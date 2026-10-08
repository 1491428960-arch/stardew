namespace StardewAI.NPC;

public sealed record GroupInvitationGenerationContext(
    int CurrentTotalDays,
    string CurrentDateLabel,
    IReadOnlyList<GroupParticipantCandidate> KnownParticipants,
    IReadOnlyList<GroupDialogueInvitationRecord> ExistingInvitations,
    IReadOnlyList<string> RecentTopicKeys,
    int? LastCreatedTotalDays,
    // 2026-10-05：已经接受「玩家有多位亲密对象」这件事的角色。可选且默认 null，
    // 现有（含测试里的）位置参数构造调用因此全部不受影响。
    IReadOnlyList<string>? AcceptedPolyamoryNpcIds = null);

public sealed class GroupInvitationGenerator
{
    private readonly IReadOnlyList<GroupInvitationTemplate> templates;

    public GroupInvitationGenerator(IReadOnlyList<GroupInvitationTemplate> templates)
    {
        this.templates = templates ?? throw new ArgumentNullException(nameof(templates));
    }

    public IReadOnlyList<GroupDialogueInvitationRecord> Generate(
        GroupInvitationGenerationContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        // dev 造的卡（Source = "dev"）是验收工具，**不参与生成器的任何历史判定** ——
        // 去重、主题冷却、一次性主题耗尽、「上一张是几人」，一处都不能看见它。
        // 否则按一下 Ctrl+Shift+F9 就会改变这个存档后面会自然长出什么。
        //
        // 在这一处滤掉，而不是在每个判定点各写一遍 `!IsDevAuthored(...)`：
        // 判定点有三处（L56 的 lastParticipantCount、L71 的 isRecentDuplicate、
        // IsThemeUnavailable），漏掉任何一处都是同一种 bug —— dev 卡偷偷吃掉
        // 玩家那次真正的机会，而且症状只在真机上过几天才显形。
        context = context with
        {
            ExistingInvitations = context.ExistingInvitations
                .Where(invitation => !IsDevAuthored(invitation))
                .ToArray(),
        };

        // 只受时间间隔约束：待处理再多也不阻止生成（用户反馈“每个刷了就得清太蠢”）。
        // 不会无限堆积的理由见 GroupInvitationRules.ShouldGenerate 的注释。
        if (!GroupInvitationRules.ShouldGenerate(
                context.CurrentTotalDays,
                context.LastCreatedTotalDays))
        {
            return Array.Empty<GroupDialogueInvitationRecord>();
        }

        var candidates = context.KnownParticipants
            .Where(candidate => candidate.HasFriendshipRecord &&
                                !string.IsNullOrWhiteSpace(candidate.NpcId) &&
                                !string.IsNullOrWhiteSpace(candidate.DisplayName))
            .GroupBy(candidate => candidate.NpcId.Trim(), StringComparer.OrdinalIgnoreCase)
            .Select(group => group.First())
            .OrderBy(candidate => candidate.NpcId, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (candidates.Length < GroupInvitationRules.MinParticipants)
        {
            return Array.Empty<GroupDialogueInvitationRecord>();
        }

        // 三人场更像群聊、两人更像私聊，所以两种规模要交替出现。
        //
        // ⚠️ 2026-09-20 修正：最初用「天数奇偶」做交替，但**生成间隔恰好也是 2 天**，
        // 于是每次生成的天数奇偶性永远相同——两人场会一直两人、三人场会一直三人。
        // 改成看**上一张邀约是几人**：上一张不足三人，这一张就优先三人。
        // 同样不引入随机数，生成结果可测、可复现。
        var lastParticipantCount = context.ExistingInvitations
            .Where(invitation => invitation.Participants is { Count: > 0 })
            .OrderByDescending(invitation => invitation.CreatedTotalDays)
            .Select(invitation => invitation.Participants.Count)
            .FirstOrDefault();
        var preferThree = candidates.Length >= GroupInvitationRules.MaxParticipants &&
                          lastParticipantCount < GroupInvitationRules.MaxParticipants;
                          foreach (var group in EnumerateGroups(candidates, preferThree))
        {
            foreach (var template in MatchingTemplates(group, context))
            {
                // 与 `GroupInvitationRules.BuildDuplicateKey` 保持同一种归一化（含模板 ID 小写），
                // 否则两边算出的键会因大小写不同而判不出重复。
                var duplicateKey = $"{template.TemplateId.Trim().ToLowerInvariant()}::{GroupInvitationRules.BuildPairKey(
                    group.Select(candidate => candidate.NpcId))}";
                var isRecentDuplicate = context.ExistingInvitations.Any(invitation =>
                    GroupInvitationRules.BuildDuplicateKey(invitation) == duplicateKey &&
                    context.CurrentTotalDays - invitation.CreatedTotalDays <
                    GroupInvitationRules.ExpirationDays);
                if (isRecentDuplicate || context.RecentTopicKeys.Contains(
                        duplicateKey,
                        StringComparer.OrdinalIgnoreCase))
                {
                    continue;
                }

                return new[] { CreateInvitation(context, template, group) };
            }
        }

        return Array.Empty<GroupDialogueInvitationRecord>();
    }

    /// <summary>
    /// 为这组人取可用模板，**并决定这次先聊哪个主题**。
    ///
    /// 排序（2026-10-09 改）：
    /// 1. 在场人数多的优先（三人场更像群聊）；
    /// 2. 打趣主题在 <see cref="GroupInvitationTemplates.CanTease"/> 成立、且不在冷却期时
    ///    **排到队首**；
    /// 3. 其余按**该主题最近一次被用到的天数**升序 —— 最久没聊过的先聊；
    /// 4. 稳定哈希兜底，避免「所有主题都没用过」时又退化成字母序。
    ///
    /// ⚠️ 第 3 条修的是一个**真实缺陷**（用户 2026-10-09 反馈「群聊全是动物」）：
    /// 此前这里最后是 `ThenBy(TemplateId, Ordinal)` —— 纯字母序，而 `Generate`
    /// 只取第一张不重复的。`animals` 以 "a" 开头，**永远排第一**，于是存档里
    /// 连续三张卡全落到「养的动物」。去重闸门也拦不住：键里含参与者组合，
    /// 换一组人、或从两人换三人，`animals` 立刻重新可用。
    ///
    /// **按需生成**：模板是按「角色 × 共同主题」算出来的，全组合预生成会有
    /// 35 万个对象（约 150 MB），对 mod 不可接受。
    /// </summary>
    private IEnumerable<GroupInvitationTemplate> MatchingTemplates(
        IReadOnlyList<GroupParticipantCandidate> group,
        GroupInvitationGenerationContext context)
    {
        var groupIds = group.Select(candidate => candidate.NpcId).ToArray();
        // 按需生成：模板由「角色 × 共同主题」算出，全组合预生成会有 35 万个对象
        // （约 150 MB），对 mod 不可接受。这里只为当前这组候选算一次。
        var generated = GroupInvitationTemplates.ForGroup(groupIds);
        var teasingReady = GroupInvitationTemplates.CanTease(
                groupIds, context.AcceptedPolyamoryNpcIds)
            && !IsThemeUnavailable(GroupInvitationTemplates.TeasingThemeId, context);

        var candidates = templates
            .Concat(generated)
            .Where(template => template.RequiredParticipants.Count == 0 ||
                template.RequiredParticipants.All(required =>
                    groupIds.Contains(required, StringComparer.OrdinalIgnoreCase)))
            .GroupBy(template => template.TemplateId, StringComparer.Ordinal)
            .Select(grouping => grouping.First())
            .ToList();

        if (teasingReady)
        {
            candidates.Add(GroupInvitationTemplates.CreateTeasing(
                groupIds, context.AcceptedPolyamoryNpcIds));
        }

        return candidates
            .OrderByDescending(template => template.RequiredParticipants.Count)
            .ThenByDescending(template => teasingReady && IsTeasing(template) ? 1 : 0)
            .ThenBy(template => ThemeLastUsedTotalDays(template, context))
            .ThenBy(template => StableHash(template.TemplateId))
            .ToArray();
    }

    private static bool IsTeasing(GroupInvitationTemplate template) =>
        string.Equals(
            ThemeIdOf(template.TemplateId),
            GroupInvitationTemplates.TeasingThemeId,
            StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// 该主题在已有邀约里**最近一次**出现的总天数；从没出现过返回
    /// <see cref="int.MinValue"/>，于是升序排在最先 —— 这就是「最久没聊过的先聊」。
    /// </summary>
    private static int ThemeLastUsedTotalDays(
        GroupInvitationTemplate template,
        GroupInvitationGenerationContext context)
    {
        var themeId = ThemeIdOf(template.TemplateId);
        return themeId.Length == 0
            ? int.MinValue
            : LastUsedTotalDays(themeId, context) ?? int.MinValue;
    }

    /// <summary>
    /// 该主题现在还能不能生成。
    ///
    /// 分两类：
    ///
    /// ① **一次性主题**（<see cref="GroupInvitationTemplates.OneShotThemeIds"/>）：
    ///    自然来过一次就**永久出局**。曾经的实现是「按
    ///    <see cref="GroupInvitationRules.ExpirationDays"/> 冷却 7 天」，2026-10-09
    ///    用户判断「多次来真的很无聊」，于是从冷却语义改成耗尽语义。
    ///    判据只看自然生成的历史，dev 入口造的卡不算 —— 见 <see cref="IsDevAuthored"/>。
    ///
    /// ② 其余主题：仍按 <see cref="GroupInvitationRules.ExpirationDays"/> 冷却 ——
    ///    与「邀约卡的生命周期」取同一个数，语义一致：一张卡还看得见的时候不会再生成第二张。
    /// </summary>
    private static bool IsThemeUnavailable(
        string themeId,
        GroupInvitationGenerationContext context)
    {
        if (GroupInvitationTemplates.OneShotThemeIds.Contains(themeId))
        {
            // ⚠ 这里**不能**复用 LastUsedTotalDays：它的语义是「最近一次是多久以前」，
            // 而过期的卡并不会从 ExistingInvitations 里消失
            // （`ExpireInvitations` 只改 Status，不删记录），
            // 所以「存在过」和「最近一次」是两件事，必须分开表达。
            //
            // 这里不必再判一次 dev 卡：Generate 入口已经把 Source = "dev" 的记录
            // 整个滤掉了，能传到这里的历史天然只有自然生成的那些。
            return context.ExistingInvitations.Any(invitation => string.Equals(
                ThemeIdOf(invitation.TemplateId),
                themeId,
                StringComparison.OrdinalIgnoreCase));
        }

        var last = LastUsedTotalDays(themeId, context);
        return last.HasValue
            && context.CurrentTotalDays - last.Value < GroupInvitationRules.ExpirationDays;
    }

    /// <summary>
    /// 这张卡是不是开发入口（Ctrl+Shift+F9 / <c>ainpc_invite</c>）造的。
    ///
    /// dev 卡不参与「一次性主题是否用过」的判定 —— 它是验收工具，
    /// 不该吃掉玩家这档真正的那一次机会。
    /// </summary>
    private static bool IsDevAuthored(GroupDialogueInvitationRecord invitation) =>
        string.Equals(
            invitation.Source,
            GroupInvitationRules.DevSource,
            StringComparison.OrdinalIgnoreCase);

    private static int? LastUsedTotalDays(
        string themeId,
        GroupInvitationGenerationContext context)
    {
        return context.ExistingInvitations
            .Where(invitation => string.Equals(
                ThemeIdOf(invitation.TemplateId), themeId, StringComparison.OrdinalIgnoreCase))
            .Select(invitation => (int?)invitation.CreatedTotalDays)
            .Max();
    }

    /// <summary>
    /// 从 `"{themeId}:{groupKey}"` 取主题前缀。旧格式（不含冒号）返回空串，
    /// 于是它既不参与轮换、也不会被误判成某个主题。
    /// </summary>
    private static string ThemeIdOf(string? templateId)
    {
        if (string.IsNullOrWhiteSpace(templateId))
        {
            return string.Empty;
        }

        var id = templateId.Trim();
        var separator = id.IndexOf(':');
        return separator > 0 ? id[..separator] : string.Empty;
    }

    /// <summary>
    /// 确定性哈希，只用来在「主题最近使用天数全部并列」时打散顺序
    /// （全新存档里所有主题都是 <see cref="int.MinValue"/>，不比这一步就会退回字母序）。
    ///
    /// **不能用 `string.GetHashCode`** —— .NET 的字符串哈希默认逐进程随机化，
    /// 会让同一份存档在不同启动之间选出不同主题，破坏代码里反复强调的
    /// 「不引入随机数，生成结果可测、可复现」。
    /// </summary>
    private static int StableHash(string value)
    {
        unchecked
        {
            var hash = 17;
            foreach (var ch in value)
            {
                hash = (hash * 31) + ch;
            }

            return hash & 0x7FFFFFFF;
        }
    }

    /// <summary>
    /// 枚举候选组合：**按 <paramref name="preferThree"/> 决定先试三人还是先试两人**。
    ///
    /// 2026-09-20：此前这里只枚举两两组合（`EnumeratePairs`），而 F9 的「自由发起」
    /// 被移除后**三人群聊就没了入口**——所以三人组合改由预设邀约承担。
    /// 规则层的 MinParticipants=2 / MaxParticipants=3 本来就允许三人，
    /// Bridge 侧也一直是 min_length=2, max_length=3，不必改动。
    /// </summary>
    private static IEnumerable<IReadOnlyList<GroupParticipantCandidate>> EnumerateGroups(
        IReadOnlyList<GroupParticipantCandidate> candidates,
        bool preferThree)
    {
        if (preferThree)
        {
            foreach (var group in EnumerateTriples(candidates))
            {
                yield return group;
            }
        }

        for (var first = 0; first < candidates.Count - 1; first++)
        {
            for (var second = first + 1; second < candidates.Count; second++)
            {
                yield return new[] { candidates[first], candidates[second] };
            }
        }

        if (!preferThree)
        {
            foreach (var group in EnumerateTriples(candidates))
            {
                yield return group;
            }
        }
    }

    /// <summary>三个候选以上才有产出；不足三个时返回空序列。</summary>
    private static IEnumerable<IReadOnlyList<GroupParticipantCandidate>> EnumerateTriples(
        IReadOnlyList<GroupParticipantCandidate> candidates)
    {
        for (var first = 0; first < candidates.Count - 2; first++)
        {
            for (var second = first + 1; second < candidates.Count - 1; second++)
            {
                for (var third = second + 1; third < candidates.Count; third++)
                {
                    yield return new[]
                    {
                        candidates[first], candidates[second], candidates[third],
                    };
                }
            }
        }
    }

    /// <summary>
    /// 开发用：**绕开冷却与去重**，直接为指定这组人造一张打趣卡。
    ///
    /// 存在理由（2026-10-09）：真机上要看到一张新打趣卡，得同时等过
    /// <see cref="GroupInvitationRules.ExpirationDays"/>（7 天）冷却、每
    /// <see cref="GroupInvitationRules.GenerationIntervalDays"/> 天一轮的生成节奏、
    /// 以及那一轮恰好挑中 ≥2 位已接受者 —— 三道闸门叠加，改一次措辞要等一周才能验一次。
    /// 这个入口把「验措辞」和「等生成」解耦，而且**不动任何冷却参数**。
    ///
    /// 走的是与正式路径同一个 <see cref="CreateInvitation"/>，因此 Topic / Title /
    /// Guidance / Expires* 与自然生成的卡逐字段一致 —— 验的就是真东西。
    /// `group` 由调用方给定：ModEntry 那边能拿到 <c>Game1</c> 取本地化显示名，这里拿不到。
    /// </summary>
    public IReadOnlyList<GroupDialogueInvitationRecord> GenerateForcedTeasing(
        int currentTotalDays,
        string currentDateLabel,
        IReadOnlyList<GroupParticipantCandidate> group)
    {
        ArgumentNullException.ThrowIfNull(group);
        var groupIds = group.Select(candidate => candidate.NpcId).ToArray();
        var template = GroupInvitationTemplates.CreateTeasing(groupIds, groupIds);
        // 空记录表 + 空 RecentTopicKeys + 空 lastCreated ⇒ 冷却与去重两道闸门自然失效，
        // 而不是靠一个 `ignoreCooldown` 开关去旁路判断逻辑（后者会让 dev 路径
        // 与正式路径的差异随时间漂移）。
        var context = new GroupInvitationGenerationContext(
            currentTotalDays,
            currentDateLabel,
            group,
            Array.Empty<GroupDialogueInvitationRecord>(),
            Array.Empty<string>(),
            null,
            groupIds);
        // Source 换成 dev：卡片其余字段与自然生成逐项一致，但生成器判断
        // 「一次性主题是否用过」时会跳过它 —— 按 Ctrl+Shift+F9 不该消耗掉
        // 玩家这档真正的那一次机会（见 GroupInvitationTemplates.OneShotThemeIds）。
        return new[] { CreateInvitation(context, template, group, GroupInvitationRules.DevSource) };
    }

    private static GroupDialogueInvitationRecord CreateInvitation(
        GroupInvitationGenerationContext context,
        GroupInvitationTemplate template,
        IReadOnlyList<GroupParticipantCandidate> group,
        string? sourceOverride = null)
    {
        var pairKey = GroupInvitationRules.BuildPairKey(group.Select(candidate => candidate.NpcId));
        return new GroupDialogueInvitationRecord
        {
            InvitationId = $"group:{template.TemplateId}:{pairKey}:{context.CurrentTotalDays}",
            TemplateId = template.TemplateId,
            Participants = group.Select(candidate => candidate.NpcId).ToArray(),
            ParticipantDisplayNames = group.Select(candidate => candidate.DisplayName).ToArray(),
            Title = template.Title,
            Topic = template.Topic,
            Guidance = template.Guidance,
            CreatedOn = context.CurrentDateLabel,
            ExpiresOn = $"day {context.CurrentTotalDays + GroupInvitationRules.ExpirationDays}",
            CreatedTotalDays = context.CurrentTotalDays,
            ExpiresTotalDays = context.CurrentTotalDays + GroupInvitationRules.ExpirationDays,
            // dev 卡走同一个入口、只换来源标记：卡片其余字段与自然生成逐项一致，
            // 这样它才既是「真卡」又不会被算进一次性主题的历史。
            Source = sourceOverride ?? template.Source,
            Status = GroupInvitationStatus.Unread,
        };
    }
}
