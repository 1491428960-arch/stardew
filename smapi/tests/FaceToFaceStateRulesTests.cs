using StardewAI.NPC;
using Microsoft.Xna.Framework;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class FaceToFaceStateRulesTests
{
    [Fact]
    public void VanillaDialogueClosingOffersContinuationOnlyOnce()
    {
        var state = FaceToFaceStateRules.StartForNpc("Rasmodia");
        state = FaceToFaceStateRules.ObserveDialogueOpened(state);
        state = FaceToFaceStateRules.ObserveDialogueClosed(state);

        Assert.Equal(FaceToFaceState.AwaitingContinuationChoice, state.State);

        state = FaceToFaceStateRules.ChooseContinuation(state, continueChat: true);
        Assert.Equal(FaceToFaceState.Composing, state.State);
        state = FaceToFaceStateRules.ObserveDialogueClosed(state);

        Assert.Equal(FaceToFaceState.AwaitingContinuationChoice, state.State);
        Assert.Equal("Rasmodia", state.NpcId);

        state = FaceToFaceStateRules.ChooseContinuation(state, continueChat: true);

        Assert.Equal(FaceToFaceState.Composing, state.State);
    }

    [Fact]
    public void EventAndFestivalNeverOfferContinuation()
    {
        var eventState = FaceToFaceStateRules.StartForNpc(
            "Rasmodia",
            eventUp: true,
            festival: false);
        var festivalState = FaceToFaceStateRules.StartForNpc(
            "Rasmodia",
            eventUp: false,
            festival: true);

        Assert.Equal(FaceToFaceState.Idle, eventState.State);
        Assert.Equal(FaceToFaceState.Idle, festivalState.State);
        Assert.Equal(FaceToFaceState.Idle,
            FaceToFaceStateRules.ObserveDialogueOpened(eventState).State);
    }

    [Fact]
    public void Continuation_question_does_not_reopen_vanilla_dialogue_state()
    {
        var state = new FaceToFaceConversationState(
            FaceToFaceState.AwaitingContinuationChoice,
            "Rasmodia");

        Assert.False(FaceToFaceStateRules.ShouldObserveDialogueOpened(state));
        Assert.True(FaceToFaceStateRules.ShouldObserveDialogueOpened(
            new FaceToFaceConversationState(
                FaceToFaceState.Idle,
                "Rasmodia")));
    }

    [Fact]
    public void Repeat_chat_requires_the_same_day_nearby_npc_and_empty_menu()
    {
        var ready = new FaceToFaceGate(
            WorldReady: true,
            MenuOpen: false,
            SameDay: true,
            SameLocation: true,
            NpcNearby: true,
            EventUp: false,
            Festival: false);

        Assert.True(FaceToFaceStateRules.CanStartRepeatChat(ready));

        Assert.False(FaceToFaceStateRules.CanStartRepeatChat(
            ready with { SameDay = false }));
    }

    /// <summary>
    /// 等价性证据（审计 #34）：续聊门槛改成 <see cref="FaceToFaceGate"/> 之后，
    /// 对全部 2^7 种取值组合的判定必须与改动前那条 7 项合取逐项一致。
    /// </summary>
    [Fact]
    public void Repeat_chat_gate_matches_the_original_seven_term_conjunction_for_every_combination()
    {
        for (var mask = 0; mask < (1 << 7); mask++)
        {
            var gate = new FaceToFaceGate(
                WorldReady: Bit(mask, 0),
                MenuOpen: Bit(mask, 1),
                SameDay: Bit(mask, 2),
                SameLocation: Bit(mask, 3),
                NpcNearby: Bit(mask, 4),
                EventUp: Bit(mask, 5),
                Festival: Bit(mask, 6));

            // 改动前的实现：
            // return worldReady && !menuOpen && sameDay && sameLocation && npcNearby &&
            //     !eventUp && !festival;
            var expected = gate.WorldReady &&
                !gate.MenuOpen &&
                gate.SameDay &&
                gate.SameLocation &&
                gate.NpcNearby &&
                !gate.EventUp &&
                !gate.Festival;

            Assert.Equal(expected, FaceToFaceStateRules.CanStartRepeatChat(gate));
        }
    }

    /// <summary>
    /// 亲吻与续聊的「七项共同条件」必须是同一个判定：同一个 gate 下，
    /// 亲吻只是在它之上再加四个玩家动作条件（审计 #33 的重复门槛已消除）。
    /// </summary>
    [Fact]
    public void Kiss_and_repeat_chat_share_the_same_gate_verdict()
    {
        for (var mask = 0; mask < (1 << 7); mask++)
        {
            var gate = new FaceToFaceGate(
                WorldReady: Bit(mask, 0),
                MenuOpen: Bit(mask, 1),
                SameDay: Bit(mask, 2),
                SameLocation: Bit(mask, 3),
                NpcNearby: Bit(mask, 4),
                EventUp: Bit(mask, 5),
                Festival: Bit(mask, 6));

            var repeatChat = FaceToFaceStateRules.CanStartRepeatChat(gate);
            var kiss = KissInteractionRules.CanTriggerKiss(
                gate,
                playerCanMove: true,
                usingTool: false,
                ridingHorse: false,
                sitting: false);

            Assert.Equal(repeatChat, kiss);
        }
    }

    private static bool Bit(int mask, int index) => (mask & (1 << index)) != 0;

    [Fact]
    public void Repeat_chat_nearby_distance_is_a_named_single_constant()
    {
        // 数值与改前 IsNearby 里的字面量 2.5f 一致（审计 #35 只抽名字，不改判定）。
        Assert.Equal(2.5f, FaceToFaceStateRules.RepeatChatNearbyDistanceInTiles);
    }

    [Fact]
    public void Repeat_chat_only_consumes_an_action_that_targets_the_remembered_npc()
    {
        var npcBounds = new Rectangle(7 * 64, 7 * 64, 64, 64);

        Assert.True(FaceToFaceStateRules.InteractionTargetsRememberedNpc(
            npcBounds,
            new Vector2(7, 7),
            tileSize: 64));
        Assert.False(FaceToFaceStateRules.InteractionTargetsRememberedNpc(
            npcBounds,
            new Vector2(8, 7),
            tileSize: 64));
    }

    [Fact]
    public void Closing_the_continuation_question_without_an_answer_ends_that_prompt()
    {
        var awaiting = new FaceToFaceConversationState(
            FaceToFaceState.AwaitingContinuationChoice,
            "Rasmodia");

        var dismissed = FaceToFaceStateRules.DismissContinuationChoice(awaiting);

        Assert.Equal(FaceToFaceState.Idle, dismissed.State);
        Assert.Null(dismissed.NpcId);
    }

    [Theory]
    [InlineData(12, 12, true)]
    [InlineData(12, 13, false)]
    [InlineData(null, 12, false)]
    public void Repeat_chat_target_is_bound_to_the_actual_game_day(
        int? rememberedDay,
        int currentDay,
        bool expected)
    {
        Assert.Equal(
            expected,
            FaceToFaceStateRules.IsSameGameDay(rememberedDay, currentDay));
    }

    [Fact]
    public void Valuable_relationship_repair_arms_a_kiss_then_completion_returns_to_repeat_chat_state()
    {
        var state = new FaceToFaceConversationState(
            FaceToFaceState.Composing,
            "Sophia");

        state = FaceToFaceStateRules.ArmKissAfterReply(state);
        Assert.Equal(FaceToFaceState.AwaitingKiss, state.State);
        Assert.Equal("Sophia", state.NpcId);

        state = FaceToFaceStateRules.BeginKiss(state);
        Assert.Equal(FaceToFaceState.Kissing, state.State);

        state = FaceToFaceStateRules.CompleteKiss(state);
        Assert.Equal(FaceToFaceState.Idle, state.State);
        Assert.Null(state.NpcId);
    }

    [Fact]
    public void Kiss_state_does_not_observe_or_offer_vanilla_dialogue()
    {
        var state = new FaceToFaceConversationState(
            FaceToFaceState.AwaitingKiss,
            "Sophia");

        Assert.False(FaceToFaceStateRules.ShouldObserveDialogueOpened(state));
        Assert.Equal(state, FaceToFaceStateRules.ObserveDialogueClosed(state));
    }

    // ── 线上频道（B26）：不进面对面状态机 ──────────────────────────────────
    //
    // 用户实测反馈：「线上聊天退出后不要弹出『继续聊聊』选项，这个是面对面聊天用的」。
    // 下面这组测试把这条设计钉在**判定**上：频道必须是续聊提问的输入之一，
    // 而不是靠「关闭回调恰好把 npc 清掉了」这种副作用侥幸不弹。

    /// <summary>
    /// 线上会话关闭一律不弹 —— 哪怕状态里还留着上次面对面的中间态、
    /// 手里还攥着一位角色。这正是用户实测到的那条路径。
    /// </summary>
    [Fact]
    public void Remote_chat_never_offers_continuation_even_with_leftover_face_to_face_state()
    {
        var leftover = new FaceToFaceConversationState(
            FaceToFaceState.AwaitingContinuationChoice,
            "Rasmodia");

        Assert.False(FaceToFaceStateRules.ShouldOfferContinuationAfterChatClosed(
            leftover,
            remoteChannelClosed: true,
            hasSpeaker: true));
    }

    /// <summary>面对面会话照旧：同一种关闭，这句提问要弹。</summary>
    [Fact]
    public void Face_to_face_chat_still_offers_continuation()
    {
        var awaiting = new FaceToFaceConversationState(
            FaceToFaceState.AwaitingContinuationChoice,
            "Rasmodia");

        Assert.True(FaceToFaceStateRules.ShouldOfferContinuationAfterChatClosed(
            awaiting,
            remoteChannelClosed: false,
            hasSpeaker: true));
    }

    /// <summary>
    /// 穷举 6 个状态 × 2 种说话人：**只有**面对面频道可能弹，
    /// 线上频道在任何组合下都不弹。这是「设计落实到所有路径」的可证伪表述。
    /// </summary>
    [Fact]
    public void Only_the_face_to_face_channel_can_offer_continuation()
    {
        foreach (var stateValue in Enum.GetValues<FaceToFaceState>())
        {
            foreach (var hasSpeaker in new[] { false, true })
            {
                var state = new FaceToFaceConversationState(stateValue, "Rasmodia");

                Assert.False(FaceToFaceStateRules.ShouldOfferContinuationAfterChatClosed(
                    state,
                    remoteChannelClosed: true,
                    hasSpeaker: hasSpeaker));

                var expected = stateValue == FaceToFaceState.AwaitingContinuationChoice &&
                    hasSpeaker;
                Assert.Equal(
                    expected,
                    FaceToFaceStateRules.ShouldOfferContinuationAfterChatClosed(
                        state,
                        remoteChannelClosed: false,
                        hasSpeaker: hasSpeaker));
            }
        }
    }

    /// <summary>
    /// 线上会话的两端都要把面对面状态收敛回空闲：被打断的 Composing／
    /// AwaitingContinuationChoice 若留着，之后任何一次 DialogueBox 关闭都会
    /// 经 ObserveDialogueClosed 把它推成那句提问。
    /// </summary>
    [Theory]
    [InlineData(FaceToFaceState.Idle)]
    [InlineData(FaceToFaceState.VanillaDialogueOpen)]
    [InlineData(FaceToFaceState.Composing)]
    [InlineData(FaceToFaceState.AwaitingContinuationChoice)]
    public void Remote_session_ends_any_face_to_face_state_back_to_idle(
        FaceToFaceState value)
    {
        var ended = FaceToFaceStateRules.EndFaceToFaceSessionForRemote(
            new FaceToFaceConversationState(value, "Rasmodia"));

        Assert.Equal(FaceToFaceState.Idle, ended.State);
        Assert.Null(ended.NpcId);
    }

    /// <summary>
    /// 亲吻两态不被线上会话打断：亲吻是面对面专属动作，线上入口本就会在
    /// 亲吻未消费时拒绝打开，所以收敛规则必须原样放过这两态。
    /// </summary>
    [Theory]
    [InlineData(FaceToFaceState.AwaitingKiss)]
    [InlineData(FaceToFaceState.Kissing)]
    public void Remote_session_leaves_kiss_states_untouched(FaceToFaceState value)
    {
        var state = new FaceToFaceConversationState(value, "Sophia");

        Assert.Equal(state, FaceToFaceStateRules.EndFaceToFaceSessionForRemote(state));
    }

    /// <summary>
    /// 端到端（规则层）：面对面聊完留下的「待续聊」中间态，中间插一次线上会话
    /// 之后不该再弹；同一条序列若不经线上，则照旧要弹。
    /// </summary>
    [Fact]
    public void A_remote_session_in_between_cancels_the_leftover_continuation_prompt()
    {
        var afterFaceToFace = FaceToFaceStateRules.ObserveDialogueClosed(
            new FaceToFaceConversationState(FaceToFaceState.Composing, "Rasmodia"));
        Assert.Equal(FaceToFaceState.AwaitingContinuationChoice, afterFaceToFace.State);

        // 线上会话两端各收敛一次（打开前 + 关闭后）。
        var closed = FaceToFaceStateRules.EndFaceToFaceSessionForRemote(
            FaceToFaceStateRules.EndFaceToFaceSessionForRemote(afterFaceToFace));

        Assert.False(FaceToFaceStateRules.ShouldOfferContinuationAfterChatClosed(
            closed,
            remoteChannelClosed: true,
            hasSpeaker: false));

        // 对照组：同样的残留状态，走的若是面对面，提问照弹。
        Assert.True(FaceToFaceStateRules.ShouldOfferContinuationAfterChatClosed(
            afterFaceToFace,
            remoteChannelClosed: false,
            hasSpeaker: true));
    }

    [Theory]
    [InlineData(ConversationChannel.Remote, true)]
    [InlineData(ConversationChannel.FaceToFace, false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    public void Only_the_remote_channel_id_is_recognized(string? channel, bool expected)
    {
        Assert.Equal(expected, FaceToFaceStateRules.IsRemoteChannel(channel));
    }

    [Fact]
    public void Remote_chat_open_rejects_a_null_state_guard()
    {
        Assert.Throws<ArgumentNullException>(() =>
            FaceToFaceStateRules.EndFaceToFaceSessionForRemote(null!));
        Assert.Throws<ArgumentNullException>(() =>
            FaceToFaceStateRules.ShouldOfferContinuationAfterChatClosed(
                null!,
                remoteChannelClosed: false,
                hasSpeaker: true));
    }
}
