"""GameMaster — 对局引擎主控."""

from __future__ import annotations

import asyncio
import json
import os
import random
import uuid
from datetime import datetime
from typing import Optional, Any

from app.llm.client import LLMClient
from app.models.enums import Role, Team, Phase, ActionType
from app.models.game import GameConfig, GameState, Player
from app.models.action import Observation, Action, ActionResult
from app.models.log import (
    GameLog,
    RoundLog,
    Message,
    ThoughtRecord,
    AgentProfile,
    AgentDecisionLog,
)
from app.agents.base import BaseAgent
from app.agents.roles.werewolf import WerewolfAgent
from app.agents.roles.seer import SeerAgent
from app.agents.roles.witch import WitchAgent
from app.agents.roles.hunter import HunterAgent
from app.agents.roles.villager import VillagerAgent
from app.engine.rules import GameRules
from app.engine.state_machine import GameStateMachine
from app.websocket.manager import GameWatchManager


class GameMaster:
    """游戏主控，管理一局狼人杀的完整流程."""

    def __init__(
        self,
        config: GameConfig,
        llm_client: Optional[LLMClient] = None,
        game_id: Optional[str] = None,
        watch_manager: Optional[GameWatchManager] = None,
    ) -> None:
        self.config = config
        self.config.validate()
        self.game_id = game_id or uuid.uuid4().hex[:12]
        self.llm = llm_client or LLMClient()
        self.rules = GameRules()
        self.state_machine = GameStateMachine()
        self.watch = watch_manager

        self.players: list[Player] = []
        self.agents: dict[int, BaseAgent] = {}
        self.game_state = GameState(game_id=self.game_id)
        self.game_log = GameLog(game_id=self.game_id, config=config.model_dump())
        self.current_round_log: Optional[RoundLog] = None

        # 日志文件路径
        log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs", "games")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"{self.game_id}.jsonl")

        # 夜间临时状态
        self.night_kills: list[int] = []
        self.night_saves: list[int] = []
        self.night_poison: Optional[int] = None
        self.seer_checks: dict[int, str] = {}  # player_id -> "good"/"werewolf"

        # 人类玩家座位（人机混战）
        self.human_seats: set[int] = set()
        self.human_inputs: dict[int, Action] = {}
        self._human_input_events: dict[int, asyncio.Event] = {}

    async def submit_human_action(self, agent_id: int, action: Action) -> None:
        """接收人类玩家的操作输入."""
        self.human_inputs[agent_id] = action
        if agent_id in self._human_input_events:
            self._human_input_events[agent_id].set()

    def validate_human_action(self, agent_id: int, action: Action) -> tuple[bool, str]:
        """校验人类玩家动作合法性. 返回 (is_valid, error_message)."""
        agent = self.agents.get(agent_id)
        if not agent:
            return False, "Agent 不存在"
        if not agent.alive:
            return False, "已死亡玩家不能操作"

        # 动作空间检查
        if action.action_type not in agent.action_space:
            return False, f"角色 {agent.role.value} 不能执行 {action.action_type.value}"

        # 阶段一致性检查
        phase = self.state_machine.current_phase
        phase_allowed: dict[Phase, list[ActionType]] = {
            Phase.NIGHT_WEREWOLF: [ActionType.KILL],
            Phase.NIGHT_SEER: [ActionType.CHECK],
            Phase.NIGHT_WITCH: [ActionType.SAVE, ActionType.POISON],
            Phase.DAY_DISCUSS: [ActionType.SPEAK],
            Phase.DAY_VOTE: [ActionType.VOTE],
            Phase.DAY_EXECUTION: [ActionType.SHOOT],
        }
        allowed = phase_allowed.get(phase, [])
        if action.action_type not in allowed and action.action_type != ActionType.PASS:
            return False, f"阶段 {phase.value} 不允许执行 {action.action_type.value}"

        # 目标校验
        if action.target_id is not None:
            if action.target_id not in self.game_state.alive_players:
                return False, "目标玩家已死亡或不存在"
            # 女巫毒药不能对自己
            if agent.role == Role.WITCH and action.action_type == ActionType.POISON and action.target_id == agent_id:
                return False, "女巫不能对自己使用毒药"

        # 去重防刷：同一轮同一 agent 已提交过
        if self.current_round_log:
            existing = [a for a in self.current_round_log.actions if a.agent_id == agent_id and a.action_type == action.action_type]
            if existing:
                return False, "该阶段已提交过动作"

        return True, ""

    async def _get_human_action(
        self,
        agent_id: int,
        observation: Observation,
        timeout: float = 300.0,
    ) -> Action:
        """等待人类玩家输入，超时则使用默认操作."""
        self._human_input_events[agent_id] = asyncio.Event()

        # 向目标人类玩家私发完整信息
        await self._broadcast_to_agent(agent_id, "human_turn", {
            "agent_id": agent_id,
            "phase": observation.phase,
            "round_num": observation.round_num,
            "available_actions": observation.available_actions,
            "observation": {
                "public_info": observation.public_info,
                "private_info": observation.private_info,
                "players_status": observation.players_status,
            },
        })
        # 向 spectators 广播脱敏版本
        await self._broadcast("human_turn", {
            "agent_id": agent_id,
            "phase": observation.phase,
            "round_num": observation.round_num,
        })

        try:
            await asyncio.wait_for(self._human_input_events[agent_id].wait(), timeout=timeout)
            return self.human_inputs.pop(agent_id, Action(agent_id=agent_id, action_type=ActionType.PASS))
        except asyncio.TimeoutError:
            print(f"  {agent_id}号人类玩家超时，自动弃票")
            return Action(agent_id=agent_id, action_type=ActionType.PASS)

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #

    async def _agent_act(self, agent_id: int, observation: Observation) -> tuple[Action, list[dict], dict]:
        """统一行动接口：人类玩家等待输入，AI 玩家直接调用 LLM.
        
        返回 (Action, LLM prompt messages, LLM response dict)
        """
        if agent_id in self.human_seats:
            action = await self._get_human_action(agent_id, observation)
            return action, [], {}
        agent = self.agents[agent_id]
        action, prompt, response = await agent.act(observation)
        # 记录决策日志
        self.game_log.agent_decisions.append(
            AgentDecisionLog(
                agent_id=agent_id,
                round_num=observation.round_num,
                phase=Phase(observation.phase),
                observation=observation.model_dump(),
                llm_prompt=json.dumps(prompt, ensure_ascii=False),
                llm_response=json.dumps(response, ensure_ascii=False),
                action=action,
            )
        )
        return action, prompt, response

    async def setup(self) -> None:
        """初始化游戏：分配角色，创建 Agent."""
        if self.agents:
            return  # 已初始化，跳过（支持外部注入 profile 后重新运行）
        roles = self.rules.role_distribution(self.config.model_dump())
        random.shuffle(roles)

        self.players = []
        self.agents = {}
        for i, role in enumerate(roles, start=1):
            team = self.rules.get_team(role)
            player = Player(player_id=i, name=f"Player{i}", role=role, team=team)
            self.players.append(player)

            agent = self._create_agent(i, role)
            self.agents[i] = agent

        self.game_state.players = self.players
        self.game_state.alive_players = [p.player_id for p in self.players if p.alive]
        self.game_log.players = [p.model_dump() for p in self.players]

        # 向 spectators 广播脱敏版本（不含 role）
        await self._broadcast("game_start", {
            "game_id": self.game_id,
            "players": [{"player_id": p.player_id, "alive": p.alive} for p in self.players],
            "config": self.config.model_dump(),
            "human_seats": list(self.human_seats),
        })
        # 向人类玩家私发含自己角色的版本
        for seat in self.human_seats:
            player = next((p for p in self.players if p.player_id == seat), None)
            if player:
                await self._broadcast_to_agent(seat, "game_start", {
                    "game_id": self.game_id,
                    "players": [{"player_id": p.player_id, "alive": p.alive} for p in self.players],
                    "my_role": player.role.value,
                    "config": self.config.model_dump(),
                    "human_seats": list(self.human_seats),
                })

        print(f"[Game {self.game_id}] 游戏初始化完成")
        print(f"  玩家: {[(p.player_id, p.role.value) for p in self.players]}")

        # 如果有人类玩家，等待一段时间让他们连接 WebSocket
        if self.human_seats:
            await asyncio.sleep(1.5)

    def _create_agent(self, player_id: int, role: Role) -> BaseAgent:
        profile = AgentProfile(role_description=self._get_role_desc(role))
        if role == Role.WEREWOLF:
            return WerewolfAgent(player_id, role, self.llm, profile)
        elif role == Role.SEER:
            return SeerAgent(player_id, role, self.llm, profile)
        elif role == Role.WITCH:
            return WitchAgent(player_id, role, self.llm, profile)
        elif role == Role.HUNTER:
            return HunterAgent(player_id, role, self.llm, profile)
        else:
            return VillagerAgent(player_id, role, self.llm, profile)

    def _get_role_desc(self, role: Role) -> str:
        descs = {
            Role.WEREWOLF: "狼人 — 夜间杀人，白天伪装",
            Role.SEER: "预言家 — 夜间查验身份",
            Role.WITCH: "女巫 — 有解药和毒药各一瓶",
            Role.HUNTER: "猎人 — 被放逐可开枪",
            Role.VILLAGER: "平民 — 无特殊技能",
        }
        return descs.get(role, "")

    # ------------------------------------------------------------------ #
    # 主循环
    # ------------------------------------------------------------------ #

    async def run(self) -> Optional[Team]:
        """运行完整对局，返回获胜阵营."""
        await self.setup()
        self.state_machine.start()
        self.game_state.round_num = 0

        max_rounds = 20  # 防止无限循环

        while self.state_machine.current_phase != Phase.GAME_OVER and self.game_state.round_num < max_rounds:
            phase = self.state_machine.current_phase
            print(f"\n{'='*40}")
            print(f"第 {self.game_state.round_num} 轮 - {phase.value}")
            print(f"{'='*40}")

            await self._broadcast("phase_change", {
                "phase": phase.value,
                "round_num": self.game_state.round_num,
                "alive_players": self.game_state.alive_players,
            })

            if phase == Phase.NIGHT_WEREWOLF:
                await self._run_night_werewolf()
            elif phase == Phase.NIGHT_SEER:
                await self._run_night_seer()
            elif phase == Phase.NIGHT_WITCH:
                await self._run_night_witch()
            elif phase == Phase.DAY_ANNOUNCE:
                await self._run_day_announce()
            elif phase == Phase.DAY_DISCUSS:
                await self._run_day_discuss()
            elif phase == Phase.DAY_VOTE:
                await self._run_day_vote()
            elif phase == Phase.DAY_EXECUTION:
                await self._run_day_execution()

            # 检查胜负
            winner = self.rules.determine_winner(self.players)
            if winner:
                self.game_state.winner = winner
                self.state_machine.end()
                if self.current_round_log:
                    self.game_log.rounds.append(self.current_round_log)
                    self.current_round_log = None
                break

            # 推进到下一阶段
            if phase != Phase.GAME_OVER:
                # 一轮结束，保存轮次日志
                if phase == Phase.DAY_EXECUTION and self.current_round_log:
                    self.game_log.rounds.append(self.current_round_log)
                    self.current_round_log = None
                self.state_machine.next()
                # 新一轮从狼人开始
                if phase == Phase.DAY_EXECUTION:
                    self.game_state.round_num += 1

        # 游戏结束
        self.game_log.winner = self.game_state.winner
        self.game_log.end_time = datetime.utcnow()
        self.game_log.total_rounds = self.game_state.round_num
        self._save_log()

        await self._broadcast("game_over", {
            "winner": self.game_state.winner.value if self.game_state.winner else None,
            "total_rounds": self.game_state.round_num,
            "players": [{"player_id": p.player_id, "role": p.role.value, "alive": p.alive} for p in self.players],
        })

        print(f"\n[Game Over] 获胜阵营: {self.game_state.winner.value if self.game_state.winner else '无'}")
        print(f"  日志已保存: {self.log_file}")
        return self.game_state.winner

    # ------------------------------------------------------------------ #
    # 各阶段逻辑
    # ------------------------------------------------------------------ #

    async def _broadcast(self, event_type: str, payload: dict) -> None:
        """通过 WebSocket 向所有观战者广播事件."""
        if self.watch is None:
            return
        await self.watch.broadcast(self.game_id, {"type": event_type, **payload})

    async def _broadcast_to_agent(self, agent_id: int, event_type: str, payload: dict) -> None:
        """通过 WebSocket 向特定玩家的连接发送事件."""
        if self.watch is None:
            return
        # 使用 agent_id 作为连接标识的查找键（前端需要在连接时声明自己的 seat）
        # 当前 watch_manager 不区分连接身份，统一广播；这里通过 payload 中的 agent_id
        # 让前端自行过滤。为了信息隔离，我们也只广播给所有连接，但 payload 里不含敏感信息。
        # 真正的点对点需要 watch_manager 支持按 seat 路由。
        # 作为过渡方案：仍然广播，但 human_turn 的敏感信息只在 payload 中，
        # 前端根据 mySeat 决定是否展示。
        await self.watch.broadcast(self.game_id, {"type": event_type, **payload})

    def _ensure_round_log(self, phase: Phase | None = None) -> None:
        """确保当前轮次日志对象已创建（每轮只创建一次）."""
        if self.current_round_log is None:
            self.current_round_log = RoundLog(
                round_num=self.game_state.round_num,
                phase=phase or Phase.NIGHT_WEREWOLF,
            )
        elif phase is not None:
            self.current_round_log.phase = phase

    async def _run_night_werewolf(self) -> None:
        """狼人讨论并选择击杀目标（支持多狼协商）."""
        self._ensure_round_log(Phase.NIGHT_WEREWOLF)
        alive_wolves = [
            a for a in self.agents.values()
            if a.role == Role.WEREWOLF and a.alive
        ]
        if not alive_wolves:
            return

        alive_status = self._get_alive_status()
        wolf_ids = [a.agent_id for a in alive_wolves]

        # 第一阶段：收集每个狼人的击杀建议
        proposals: list[dict] = []
        for wolf in alive_wolves:
            obs = Observation(
                phase=Phase.NIGHT_WEREWOLF.value,
                round_num=self.game_state.round_num,
                available_actions=["kill"],
                private_info=f"你的狼队友是: {[w for w in wolf_ids if w != wolf.agent_id]}号",
                players_status=alive_status,
            )
            action, _prompt, _response = await self._agent_act(wolf.agent_id, obs)

            target = action.target_id
            if target and target in self.game_state.alive_players:
                proposals.append({
                    "agent_id": wolf.agent_id,
                    "target_id": target,
                    "reasoning": action.reasoning,
                })
                print(f"  狼人{wolf.agent_id}号 提议击杀 {target}号")
            else:
                print(f"  狼人{wolf.agent_id}号 未提出有效目标")

            self._record_action(wolf.agent_id, action)

        if not proposals:
            print("  狼人阵营无有效提议，跳过击杀")
            return

        # 统计第一轮建议
        targets = [p["target_id"] for p in proposals]
        if len(set(targets)) == 1:
            # 全票一致，直接执行
            final_target = targets[0]
            print(f"  狼人阵营一致决定击杀 {final_target}号")
        else:
            # 第二阶段：协商投票
            proposal_info = "\n".join([
                f"  狼人{p['agent_id']}号提议刀{p['target_id']}号: {p['reasoning'][:60]}"
                for p in proposals
            ])

            final_votes: dict[int, int] = {}
            for wolf in alive_wolves:
                obs = Observation(
                    phase=Phase.NIGHT_WEREWOLF.value,
                    round_num=self.game_state.round_num,
                    available_actions=["kill"],
                    private_info=(
                        f"你的狼队友是: {[w for w in wolf_ids if w != wolf.agent_id]}号\n"
                        f"协商阶段，队友提议如下:\n{proposal_info}\n"
                        "请根据团队利益，重新选择今晚的击杀目标。"
                    ),
                    players_status=alive_status,
                )
                action, _prompt, _response = await self._agent_act(wolf.agent_id, obs)

                if action.target_id and action.target_id in self.game_state.alive_players:
                    final_votes[wolf.agent_id] = action.target_id
                    print(f"  狼人{wolf.agent_id}号 协商后投票击杀 {action.target_id}号")

                self._record_action(wolf.agent_id, action)

            # 统计最终票数
            if final_votes:
                vote_counts: dict[int, int] = {}
                for target in final_votes.values():
                    vote_counts[target] = vote_counts.get(target, 0) + 1

                max_votes = max(vote_counts.values())
                candidates = [t for t, c in vote_counts.items() if c == max_votes]
                final_target = random.choice(candidates)

                print(f"  狼人阵营协商后决定击杀 {final_target}号（{max_votes}票）")
            else:
                # 无人投票，采用第一轮第一个提议
                final_target = proposals[0]["target_id"]
                print(f"  狼人阵营无协商结果，默认击杀 {final_target}号")

        self.night_kills.append(final_target)

        # 记录最终击杀目标到日志（用于 metrics 计算首刀命中率）
        result_msg = Message(
            round_num=self.game_state.round_num,
            phase=Phase.NIGHT_WEREWOLF,
            speaker_id=0,
            content=f"狼人阵营最终决定击杀 {final_target}号",
            msg_type="system",
        )
        for a in self.agents.values():
            if a.alive and a.role == Role.WEREWOLF:
                a.receive_public_message(result_msg)
        if self.current_round_log:
            self.current_round_log.messages.append(result_msg)

    async def _run_night_seer(self) -> None:
        """预言家查验."""
        self._ensure_round_log(Phase.NIGHT_SEER)
        seers = [a for a in self.agents.values() if a.role == Role.SEER and a.alive]
        if not seers:
            return

        alive_status = self._get_alive_status()
        seer = seers[0]
        obs = Observation(
            phase=Phase.NIGHT_SEER.value,
            round_num=self.game_state.round_num,
            available_actions=["check"],
            players_status=alive_status,
        )
        action, prompt, response = await self._agent_act(seer.agent_id, obs)

        target = action.target_id
        result_str = ""
        if target and target in self.game_state.alive_players:
            target_player = next(p for p in self.players if p.player_id == target)
            result = "werewolf" if target_player.role == Role.WEREWOLF else "good"
            self.seer_checks[target] = result
            result_str = result
            print(f"  预言家{seer.agent_id}号 -> 查验 {target}号 = {result}")

            # 通知预言家结果
            obs.private_info = f"查验结果: {target}号 是 {result}"
        else:
            print(f"  预言家{seer.agent_id}号 -> 未选择目标")

        self._record_action(seer.agent_id, action)
        self._record_action_result(action, True, result_str)

    async def _run_night_witch(self) -> None:
        """女巫行动."""
        self._ensure_round_log(Phase.NIGHT_WITCH)
        witches = [a for a in self.agents.values() if isinstance(a, WitchAgent) and a.alive]
        if not witches:
            return

        witch = witches[0]
        alive_status = self._get_alive_status()

        # 告知女巫今晚谁被刀了
        killed_info = ""
        if self.night_kills:
            killed_info = f"今晚 {self.night_kills[0]}号 被狼人杀了。"

        obs = Observation(
            phase=Phase.NIGHT_WITCH.value,
            round_num=self.game_state.round_num,
            available_actions=[a.value for a in witch.action_space],
            private_info=killed_info + f" 解药剩余: {'有' if witch.has_antidote else '无'} | 毒药剩余: {'有' if witch.has_poison else '无'}",
            players_status=alive_status,
        )
        action, prompt, response = await self._agent_act(witch.agent_id, obs)
        target_str = f" {action.target_id}号" if action.target_id else ""
        print(f"  女巫{witch.agent_id}号 -> {action.action_type.value}{target_str}")

        save_result_msg = ""
        if action.action_type == ActionType.SAVE and witch.has_antidote:
            if self.night_kills:
                # 女巫自救规则：仅第一夜可自救
                if self.game_state.round_num > 1 and self.night_kills[0] == witch.agent_id:
                    print(f"  女巫{witch.agent_id}号 第二夜及以后不能自救，save 无效")
                    save_result_msg = "失败：第二夜及以后不能自救"
                else:
                    self.night_saves.append(self.night_kills[0])
                    witch.has_antidote = False
                    save_result_msg = f"成功救下 {self.night_kills[0]}号"
        elif action.action_type == ActionType.POISON and witch.has_poison:
            if action.target_id and action.target_id in self.game_state.alive_players:
                self.night_poison = action.target_id
                witch.has_poison = False
                save_result_msg = f"成功毒杀 {action.target_id}号"

        self._record_action(witch.agent_id, action)
        self._record_action_result(action, True, save_result_msg)

    async def _run_day_announce(self) -> None:
        """公布夜间死亡信息."""
        self._ensure_round_log(Phase.DAY_ANNOUNCE)
        deaths = []
        death_reasons: dict[int, str] = {}

        # 计算实际死亡
        for killed in self.night_kills:
            if killed not in self.night_saves:
                deaths.append(killed)
                death_reasons[killed] = "werewolf_kill"
        if self.night_poison and self.night_poison not in deaths:
            deaths.append(self.night_poison)
            death_reasons[self.night_poison] = "poison"

        # 去重并排序
        deaths = sorted(set(deaths))

        announcement = (
            f"天亮了。昨夜 {'、'.join([f'{d}号' for d in deaths])} 死亡"
            if deaths else "天亮了。昨夜是平安夜。"
        )
        print(f"  {announcement}")

        # 广播给所有存活玩家
        msg = Message(
            round_num=self.game_state.round_num,
            phase=Phase.DAY_ANNOUNCE,
            speaker_id=0,
            content=announcement,
            msg_type="system",
        )
        for agent in self.agents.values():
            if agent.alive:
                agent.receive_public_message(msg)
        if self.current_round_log:
            self.current_round_log.messages.append(msg)

        # 处理死亡（猎人夜间被刀可开枪，被毒不能开枪）
        for pid in deaths:
            self._kill_player(pid, reason=death_reasons.get(pid, "night"))
            await self._broadcast("death_announce", {
                "player_id": pid,
                "reason": death_reasons.get(pid, "night"),
                "round_num": self.game_state.round_num,
            })

        # 猎人夜间死亡开枪结算
        for pid in deaths:
            player = next((p for p in self.players if p.player_id == pid), None)
            if player and player.role == Role.HUNTER and death_reasons.get(pid) != "poison":
                hunter_agent = self.agents[pid]
                alive_status = self._get_alive_status()
                obs = Observation(
                    phase=Phase.DAY_EXECUTION.value,
                    round_num=self.game_state.round_num,
                    available_actions=["shoot"],
                    private_info="你夜间死亡了，可以选择开枪带走一人",
                    players_status=alive_status,
                )
                action, prompt, response = await self._agent_act(hunter_agent.agent_id, obs)
                if action.target_id and action.target_id in self.game_state.alive_players:
                    print(f"  猎人{pid}号 -> 夜间死亡开枪带走 {action.target_id}号")
                    self._kill_player(action.target_id, reason="hunter_shoot")
                    await self._broadcast("death_announce", {
                        "player_id": action.target_id,
                        "reason": "hunter_shoot",
                        "round_num": self.game_state.round_num,
                    })
                else:
                    print(f"  猎人{pid}号 -> 夜间死亡选择不开枪")
                self._record_action(hunter_agent.agent_id, action)
                self._record_action_result(action, True, "")

        # 重置夜间状态
        self.night_kills = []
        self.night_saves = []
        self.night_poison = None

    async def _run_day_discuss(self) -> None:
        """白天发言阶段（简化：每个存活Agent依次发言）."""
        self._ensure_round_log(Phase.DAY_DISCUSS)
        alive_agents = [a for a in self.agents.values() if a.alive]
        random.shuffle(alive_agents)  # 随机发言顺序

        alive_status = self._get_alive_status()

        for agent in alive_agents:
            # 为预言家附加查验信息
            private_info = ""
            if agent.role == Role.SEER and self.seer_checks:
                checks_str = ", ".join(
                    [f"{k}号是{v}" for k, v in self.seer_checks.items()]
                )
                private_info = f"你过往的查验记录: {checks_str}"

            obs = Observation(
                phase=Phase.DAY_DISCUSS.value,
                round_num=self.game_state.round_num,
                available_actions=["speak"],
                public_info=f"当前存活: {[a.agent_id for a in alive_agents]}",
                private_info=private_info,
                players_status=alive_status,
            )
            action, prompt, response = await self._agent_act(agent.agent_id, obs)

            content = action.content or "...（沉默）"
            print(f"  [{agent.agent_id}号/{agent.role.value}] {content[:80]}")

            msg = Message(
                round_num=self.game_state.round_num,
                phase=Phase.DAY_DISCUSS,
                speaker_id=agent.agent_id,
                content=content,
                msg_type="speak",
            )
            # 广播给所有人
            for a in self.agents.values():
                a.receive_public_message(msg)
            if self.current_round_log:
                self.current_round_log.messages.append(msg)

            await self._broadcast("public_chat", {
                "round_num": self.game_state.round_num,
                "speaker_id": agent.agent_id,
                "content": content,
            })

            self._record_action(agent.agent_id, action)

    async def _run_day_vote(self) -> None:
        """投票阶段."""
        self._ensure_round_log(Phase.DAY_VOTE)
        alive_agents = [a for a in self.agents.values() if a.alive]
        alive_status = self._get_alive_status()

        votes: dict[int, int] = {}  # voter_id -> target_id

        for agent in alive_agents:
            obs = Observation(
                phase=Phase.DAY_VOTE.value,
                round_num=self.game_state.round_num,
                available_actions=["vote"],
                players_status=alive_status,
            )
            action, prompt, response = await self._agent_act(agent.agent_id, obs)

            if action.target_id and action.target_id in self.game_state.alive_players:
                votes[agent.agent_id] = action.target_id
                print(f"  {agent.agent_id}号 -> 投票给 {action.target_id}号")
            else:
                print(f"  {agent.agent_id}号 -> 弃票")

            self._record_action(agent.agent_id, action)

        # 计票
        if votes:
            vote_counts: dict[int, int] = {}
            for target in votes.values():
                vote_counts[target] = vote_counts.get(target, 0) + 1
            max_votes = max(vote_counts.values())
            candidates = [p for p, c in vote_counts.items() if c == max_votes]
            executed = random.choice(candidates)  # 平票随机

            announcement = f"投票结果: {executed}号 被放逐（{max_votes}票）"
            print(f"  {announcement}")

            msg = Message(
                round_num=self.game_state.round_num,
                phase=Phase.DAY_VOTE,
                speaker_id=0,
                content=announcement,
                msg_type="system",
            )
            for a in self.agents.values():
                if a.alive:
                    a.receive_public_message(msg)

            await self._broadcast("vote_update", {
                "round_num": self.game_state.round_num,
                "votes": votes,
                "executed": executed,
                "max_votes": max_votes,
            })

            # 记录被放逐者，在执行阶段结算
            self._pending_execution = executed
        else:
            print("  无人投票，跳过放逐")
            self._pending_execution = None

    async def _run_day_execution(self) -> None:
        """执行放逐."""
        self._ensure_round_log(Phase.DAY_EXECUTION)
        if hasattr(self, "_pending_execution") and self._pending_execution:
            pid = self._pending_execution
            player = next(p for p in self.players if p.player_id == pid)

            # 猎人被放逐可以开枪
            if player.role == Role.HUNTER:
                hunter_agent = self.agents[pid]
                alive_status = self._get_alive_status()
                obs = Observation(
                    phase=Phase.DAY_EXECUTION.value,
                    round_num=self.game_state.round_num,
                    available_actions=["shoot"],
                    private_info="你已被放逐，可以选择开枪带走一人",
                    players_status=alive_status,
                )
                action, prompt, response = await self._agent_act(hunter_agent.agent_id, obs)
                if action.target_id and action.target_id in self.game_state.alive_players:
                    print(f"  猎人{pid}号 -> 开枪带走 {action.target_id}号")
                    self._kill_player(action.target_id, reason="hunter_shoot")
                else:
                    print(f"  猎人{pid}号 -> 选择不开枪")
                self._record_action(hunter_agent.agent_id, action)
                self._record_action_result(action, True, "")

            self._kill_player(pid, reason="vote")
            await self._broadcast("death_announce", {
                "player_id": pid,
                "reason": "vote",
                "round_num": self.game_state.round_num,
            })
            delattr(self, "_pending_execution")

    # ------------------------------------------------------------------ #
    # 辅助方法
    # ------------------------------------------------------------------ #

    def _get_alive_status(self) -> list[dict]:
        """获取存活玩家状态（不含角色信息）."""
        return [
            {"player_id": p.player_id, "alive": p.alive}
            for p in self.players
        ]

    def _kill_player(self, player_id: int, reason: str = "") -> None:
        """杀死一名玩家."""
        player = next((p for p in self.players if p.player_id == player_id), None)
        if player and player.alive:
            player.alive = False
            if player_id in self.game_state.alive_players:
                self.game_state.alive_players.remove(player_id)
            if player_id in self.agents:
                self.agents[player_id].on_death()
            # 记录死亡到轮次日志
            if self.current_round_log is not None:
                if player_id not in self.current_round_log.deaths:
                    self.current_round_log.deaths.append(player_id)
            print(f"  {player_id}号 死亡 ({reason})")

    def _record_action(self, agent_id: int, action: Action) -> None:
        """记录动作到当前轮次日志."""
        if self.current_round_log is not None:
            self.current_round_log.actions.append(action)

    def _record_action_result(self, action: Action, success: bool, message: str) -> None:
        """记录动作结果到当前轮次日志."""
        if self.current_round_log is not None:
            self.current_round_log.results.append(
                ActionResult(
                    action=action,
                    success=success,
                    message=message,
                )
            )

    def _save_log(self) -> None:
        """将游戏日志写入 JSON Lines 文件."""
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                # 写入游戏元数据
                meta = {
                    "type": "game_meta",
                    "game_id": self.game_log.game_id,
                    "config": self.game_log.config,
                    "players": self.game_log.players,
                    "winner": self.game_log.winner.value if self.game_log.winner else None,
                    "start_time": self.game_log.start_time.isoformat() if self.game_log.start_time else None,
                    "end_time": self.game_log.end_time.isoformat() if self.game_log.end_time else None,
                    "total_rounds": self.game_log.total_rounds,
                }
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")

                # 写入每轮日志
                for rnd in self.game_log.rounds:
                    f.write(json.dumps(rnd.model_dump(mode="json"), ensure_ascii=False) + "\n")

                # 写入决策日志（独立 section）
                if self.game_log.agent_decisions:
                    f.write(json.dumps({"type": "agent_decisions", "decisions": [d.model_dump(mode="json") for d in self.game_log.agent_decisions]}, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"  日志保存失败: {e}")

    # ------------------------------------------------------------------ #
    # 复盘与反思
    # ------------------------------------------------------------------ #

    async def post_game_reflection(self) -> dict[int, AgentProfile]:
        """触发所有Agent的局后反思."""
        updated_profiles = {}
        for player in self.players:
            agent = self.agents[player.player_id]
            won = player.team == self.game_state.winner

            # 提取该Agent的关键决策
            key_decisions = []  # 简化：可以从日志中提取

            # 构造对局日志摘要
            log_summary = f"游戏结果: {'胜利' if won else '失败'}。"
            log_summary += f" 存活到第{self.game_state.round_num}轮。"

            try:
                new_profile = await agent.reflect_after_game(
                    game_log=log_summary,
                    won=won,
                    key_decisions=key_decisions,
                )
                updated_profiles[player.player_id] = new_profile
            except Exception as e:
                print(f"  Agent {player.player_id} 反思失败: {e}")

        return updated_profiles
