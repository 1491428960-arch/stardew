namespace StardewAI.NPC;

/// <summary>
/// 开发用**示例聊天记录**：给「F8 面板往上翻历史」与「记录随存档持久化」这两条链路
/// 准备一批看得见、翻得动的假数据。
///
/// 为什么需要它：玩家自己还没聊过几句，F8 里自然没有历史可翻 —— 功能做完了却验收不了。
/// 这里造一批像真对话的记录（玩家短句 + NPC 有角色感的回复），由
/// <see cref="BridgeClient.InjectSampleHistory"/> 灌进**内存里的回看档案**；
/// 之后玩家按自己平时的习惯保存，记录就随存档落盘，关掉游戏再进来依然翻得到。
///
/// 五条边界：
/// 1. **不碰存档文件**：本类只生产数据，写内存那一头在 <see cref="BridgeClient"/>，
///    落盘完全交给玩家自己的正常保存（SMAPI 的 Saving）。mod 不直接写任何存档文件；
/// 2. **不碰发给模型的窗口**：示例只进回看档案（<c>displayHistoryByNpc</c>），
///    不进发送窗口（<c>historyByNpc</c>）—— 所以 NPC 不会"记得"玩家没说过的话。
///    翻得到、聊不到，这是有意的；
/// 3. **可清理**：每条示例都带 <see cref="MarkerIntent"/> 标记，写在 <c>Intent</c> 字段上。
///    真实对话的 Intent 是 chat/item/topic，群聊摘要是 null，不会撞车；
///    清理时只按标记删，玩家真实聊过的记录一条不动；
/// 4. **重复注入不翻倍**：注入前先按标记清掉上一批，所以连按几次键结果一样；
/// 5. **尺寸在规格内**：每条内容都远短于 <see cref="ChatHistoryRules.MaxContentLength"/>，
///    条数也在 <see cref="ChatHistoryRules.MaxDisplayMessages"/> 的裁剪规则之内
///    （唯一的例外是 <see cref="BuildStress"/>，它**故意**超限，用来验证裁掉最旧的）。
/// </summary>
public static class SampleChatHistory
{
    /// <summary>
    /// 示例记录的标记。写在 <see cref="BridgeDialogueHistoryItem.Intent"/> 上：
    /// 这个字段只随记录存下来、不参与面板显示，也不会被
    /// <see cref="ChatHistoryArchive"/> 的读回流程丢掉，所以落盘之后仍然认得出来。
    /// </summary>
    public const string MarkerIntent = "sample";

    public const string AbigailId = "Abigail";
    public const string PennyId = "Penny";
    public const string ShaneId = "Shane";
    public const string EmilyId = "Emily";

    /// <summary>压力注入默认落在哪位 NPC 身上。</summary>
    public const string StressNpcId = AbigailId;

    /// <summary>
    /// 压力注入的条数：比 <see cref="ChatHistoryRules.MaxDisplayMessages"/> 多
    /// <see cref="StressDroppedMessages"/> 条，正好能验证「超过上限裁掉最旧的」。
    /// </summary>
    public const int StressMessageCount = ChatHistoryRules.MaxDisplayMessages + StressDroppedMessages;

    /// <summary>压力注入应当被裁掉的条数（= 超出上限的那一截）。</summary>
    public const int StressDroppedMessages = 42;

    /// <summary>示例覆盖的角色：都在玩家日常动线上，白天或傍晚容易碰到。</summary>
    public static readonly IReadOnlyList<string> NpcIds =
        new[] { AbigailId, PennyId, ShaneId, EmilyId };

    private static readonly string[] SeasonNames = new[] { "春", "夏", "秋", "冬" };

    private const int DaysPerSeason = 28;

    /// <summary>
    /// 四位角色的示例对话：每位 15 轮（30 条），写的是玩家与 NPC 的日常闲聊。
    /// 角色语气刻意拉开距离 —— 阿比盖尔莽撞爱冒险、潘妮温和爱读书、
    /// 谢恩别扭地嘴硬、艾米丽热情跳脱 —— 这样"往上翻"时一眼能看出是谁在说。
    /// </summary>
    private static readonly (string Player, string Npc)[] AbigailTurns = new[]
    {
        ("今天有空吗？", "有啊，我正打算去矿洞逛逛。你要一起吗？我准备了两把剑……其中一把是我爸的。"),
        ("你爸知道吗？", "不知道，而且他最好一直不知道。他昨天还在念叨矿洞太危险，转头自己去镇上买了两打鸡蛋。"),
        ("那你打算下到第几层？", "至少二十层吧，我想再找一块紫水晶。上次那块我摆在窗台上，晚上会发光，特别好看。"),
        ("我上次在十五层碰到一堆史莱姆。", "史莱姆其实好对付，只要别一次引三只。别问我怎么知道的。"),
        ("听起来有故事。", "那天我浑身黏糊糊地回家，我妈看了我一眼，什么都没说，直接让我把衣服脱在门廊上。"),
        ("你平时在家都做什么？", "打游戏，或者练鼓。我妈说我打鼓像在拆房子，我一直当那是夸奖。"),
        ("你会打什么曲子？", "最近在练一首很吵的。Sebastian 听完只说了一句“还行”——你知道的，从他嘴里这已经是最高评价了。"),
        ("你们经常一起玩？", "偶尔。他玩得比我好，但他从来不说。这点我挺讨厌的，也挺佩服。"),
        ("晚上去镇上吗？", "去，我约了人。……好吧，其实是我想去墓地那边看看有没有什么动静，最近总觉得那儿怪怪的。"),
        ("你胆子真大。", "怕的时候我也会跑。区别只是我跑之前会先看清楚是什么东西。"),
        ("你爸店里最近进新货了吗？", "进了一箱新种子，他藏在柜台下面，说是给熟客留的。我猜他是怕我妈发现他又乱进货。"),
        ("我今天挖到一块很奇怪的石头。", "什么样的？如果是带纹路的那种，别扔，我拿两块矿石跟你换。"),
        ("下次带给你看。", "说定了。你要是敢忘，我就去你农场门口站着，站到你出来为止。"),
        ("那你爸的剑你打算还回去吗？", "等我找到一把更好的再说。或者等他先发现。这两个哪个先来都算我赢。"),
        ("那明天矿洞见？", "好。带上你的剑，还有——多带点吃的。上次你饿着肚子往下走，我可不想再把你背上来。"),
    };

    private static readonly (string Player, string Npc)[] PennyTurns = new[]
    {
        ("你在看书吗？", "嗯，是一本讲山谷植物的旧书。文字有点老，但插图特别漂亮。"),
        ("讲的什么？", "主要是野花的花期。原来蒲公英在春天开得最早，也最先被孩子摘光——Vincent 上周就送了我一把。"),
        ("你平时教他们读书？", "每周几次。Jas 认字很快，Vincent 更喜欢听，所以我会念给他听，再让他复述一遍。"),
        ("他们听话吗？", "大部分时候。有一次 Vincent 把蚯蚓带进了图书馆，馆长差点昏过去，不过他自己也吓得不轻。"),
        ("你妈妈最近还好吗？", "老样子。她最近在攒钱想修一下车，不过……嗯，她总有更要紧的开销。"),
        ("需要帮忙的话跟我说。", "谢谢你，真的。不过我们还好，日子紧一点，也还是过得下去的。"),
        ("你以后想做什么？", "我想有个自己的小房子，不用很大，能有一扇朝南的窗，让阳光照进来就够了。"),
        ("那一定很好看。", "我在脑子里已经布置过很多遍了。窗台上放几盆花，书架靠墙，桌上留一盏灯。"),
        ("今天天气真好。", "是啊。我早上在河边坐了一会儿，水声让人很安静。有时候我会想，这个山谷一直在照顾我们。"),
        ("你常去河边？", "凉快的时候去。夏天我会带一本书，但其实常常看着水面就走神了。"),
        ("农场最近很忙。", "看得出来，你手上的茧比上次见你时多了。……抱歉，我是不是观察得太细了。"),
        ("没事，我不介意。", "那就好。你哪天要是累得不想做饭，可以来我这儿，我煮的汤还算能喝。"),
        ("什么汤？", "南瓜汤，或者土豆浓汤。食谱是我外婆留下来的，纸都黄了，字还认得出来。"),
        ("Jas 最近在写什么？", "一首很短的诗，写的是她家院子里那棵树。她说树会听人说话，我觉得她大概是对的。"),
        ("那我明天来帮你修窗户。", "你愿意的话……那太好了。我会提前把工具找出来，我妈的工具箱里什么都有，就是什么都找不到。"),
    };

    private static readonly (string Player, string Npc)[] ShaneTurns = new[]
    {
        ("在忙吗？", "在数鸡。……别笑，真的在数。少一只我今晚就别想睡了。"),
        ("都齐吗？", "齐了。Charlie 又跑到角落去了，它总觉得自己是只野鸡。"),
        ("你在 Joja 上班累吗？", "还行。搬箱子，摆货架，重复。至少不用动脑子。"),
        ("你养鸡多久了？", "比我愿意承认的久。一开始只是想有个理由不出门，后来发现它们比大多数人好相处。"),
        ("它们都有名字吗？", "大部分没有。除了 Charlie。你要是敢说出去我给鸡起名字，我就当没认识过你。"),
        ("我什么都没听见。", "很好。……你学得挺快。"),
        ("晚上去酒吧吗？", "去。不过别以为我是去喝闷酒的，我主要是去看球。"),
        ("今天有比赛？", "没有。所以只能喝闷酒了。"),
        ("Jas 最近怎么样？", "挺好。她最近迷上画画，画了一堆鸡，全是我家的。她姨母说那是艺术，我看着像鸡蛋。"),
        ("你会去看她的画展吗？", "……如果她办的话。别用那种眼神看我，我会去的。"),
        ("农场那边最近挺安静的。", "安静是好事。镇上吵起来的时候，通常都不是什么好消息。"),
        ("你以前在城里待过？", "待过。不想聊这个。……总之现在在这儿，挺好的。"),
        ("那我不问了。", "谢了，真心的。不是所有人都知道什么时候该闭嘴。"),
        ("Charlie 今天怎么样？", "还是老样子，一见我就叫。……行吧，你问它干什么。它挺好的。"),
        ("明天见。", "嗯，明天见。要是你早上过来，我可能还剩点鸡蛋——别指望我给你留，但也不是没可能。"),
    };

    private static readonly (string Player, string Npc)[] EmilyTurns = new[]
    {
        ("今天在忙什么？", "在给一条旧裙子改花样！我跟你说，有时候布料自己会告诉你想变成什么样子。"),
        ("真的假的？", "当然是真的。你不信的话下次来看——颜色会从针脚里慢慢浮出来，像太阳出来一样。"),
        ("你妹妹也喜欢做衣服吗？", "Haley？她更喜欢穿。不过她拍照前会来问我怎么配色，这就是她的方式。"),
        ("你们关系很好。", "我们小时候天天吵架。现在……现在会互相留灯。这个变化我等了很多年。"),
        ("你那些水晶是做什么的？", "有的用来配色，有的用来提醒我。紫水晶提醒我别急，黄水晶提醒我多笑。"),
        ("管用吗？", "你笑一下试试？看，管用了吧。"),
        ("晚上在酒吧上班？", "对，四点开始。你要是来，我给你调一杯没有酒精的，加了薄荷和柠檬，你会喜欢的。"),
        ("你怎么知道我喜欢？", "我不知道呀，我猜的。猜错了我们再换一杯，这又不是什么大事。"),
        ("谢谢你总是这么开心。", "我也不是一直开心的。只是我发现，难过的时候把自己关起来，难受的时间反而更长。"),
        ("那你会怎么办？", "跳舞。真的。在厨房放很吵的音乐，跳得很难看，跳到出汗，然后就没事了。"),
        ("下次我不敢看了。", "你一定要看！这是很重要的体验，关于勇气，也关于接受自己笨手笨脚。"),
        ("你养的那只鹦鹉呢？", "它学会了我妹妹的名字，现在每天喊“Haley！Haley！”，我妹妹快疯了。我觉得特别好笑。"),
        ("它还会说什么？", "还会学我叹气。这个就比较伤人了。"),
        ("你的舞最近练得怎么样？", "昨天转圈的时候撞到了门框。不过没关系，门框也没有怪我。"),
        ("改天我去看它。", "来呀！我提前把茶煮上。你进门的时候它可能会冲你喊 Haley，你别介意。"),
    };

    /// <summary>
    /// 造一批示例记录：四位角色，每位 15 轮（30 条），按时间先后排列（最新的在最后）。
    /// 返回值可直接交给 <see cref="BridgeClient.InjectSampleHistory"/>。
    /// </summary>
    public static IReadOnlyDictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>> Build()
    {
        return new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
        {
            [AbigailId] = Expand(AbigailTurns),
            [PennyId] = Expand(PennyTurns),
            [ShaneId] = Expand(ShaneTurns),
            [EmilyId] = Expand(EmilyTurns),
        };
    }

    /// <summary>
    /// 压力注入：给一位 NPC 造 <paramref name="totalMessages"/> 条记录，用来验证
    /// 「超过 <see cref="ChatHistoryRules.MaxDisplayMessages"/> 条会裁掉最旧的」。
    ///
    /// 内容不是手写的，是**合成流水**：每一轮算游戏里的一天，句首带日期戳
    /// （<c>第1年 春22日 …</c>），玩家句与 NPC 句各从一个日常句池里轮取。
    /// 所以它读起来像一段跨了很多年的流水账，而不是"测试1、测试2"——
    /// 但它不是给玩家品味的内容，只用来把"裁掉最旧的"这件事变得**一眼可验**：
    /// 注入 <see cref="StressMessageCount"/> 条之后，面板最上面那条应当是
    /// <see cref="StressFirstKeptStamp"/>（它前面正好被裁掉 <see cref="StressDroppedMessages"/> 条）。
    /// </summary>
    public static IReadOnlyDictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>> BuildStress(
        string npcId,
        int totalMessages = StressMessageCount)
    {
        var items = new List<BridgeDialogueHistoryItem>(Math.Max(totalMessages, 0));
        for (var index = 0; index < totalMessages; index++)
        {
            var playerTurn = index % 2 == 0;
            var day = index / 2;
            var line = playerTurn
                ? StressPlayerLines[day % StressPlayerLines.Length]
                : StressNpcLines[day % StressNpcLines.Length];
            items.Add(new BridgeDialogueHistoryItem
            {
                Role = playerTurn ? "user" : "assistant",
                Content = $"{DayStamp(day)} {line}",
                Intent = MarkerIntent,
            });
        }

        return new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
        {
            [npcId] = items,
        };
    }

    /// <summary>
    /// 压力注入被裁到上限之后，面板最上面那条应当带的日期戳。
    /// 用于测试与「怎么算验证通过」的说明，避免这个数字在几处各写一遍。
    /// </summary>
    public static string StressFirstKeptStamp => DayStamp(StressDroppedMessages / 2);

    /// <summary>某条记录是不是示例（按 <see cref="MarkerIntent"/> 标记判定）。</summary>
    public static bool IsSample(BridgeDialogueHistoryItem? item)
    {
        return string.Equals(item?.Intent?.Trim(), MarkerIntent, StringComparison.Ordinal);
    }

    /// <summary>
    /// 把（玩家句，NPC 句）的轮次摊平成消息序列：一轮两条，玩家的在前。
    /// 与真实记录一致：<c>user</c> 是玩家说的，<c>assistant</c> 是 NPC 说的。
    /// </summary>
    private static IReadOnlyList<BridgeDialogueHistoryItem> Expand((string Player, string Npc)[] turns)
    {
        var items = new List<BridgeDialogueHistoryItem>(turns.Length * 2);
        foreach (var (player, npc) in turns)
        {
            items.Add(Sample(player, "user"));
            items.Add(Sample(npc, "assistant"));
        }

        return items;
    }

    private static BridgeDialogueHistoryItem Sample(string content, string role)
    {
        return new BridgeDialogueHistoryItem
        {
            Role = role,
            Content = content,
            Intent = MarkerIntent,
        };
    }

    /// <summary>
    /// 第 <paramref name="zeroBasedDay"/> 天在游戏历法里的写法（四季各 28 天，一年 112 天）。
    /// 只用于压力注入的日期戳：让一千多条合成记录看起来像一段真实的长期流水，
    /// 同时让"最上面那条是哪一天"成为可核对的刻度。
    /// </summary>
    private static string DayStamp(int zeroBasedDay)
    {
        var day = Math.Max(zeroBasedDay, 0);
        var year = day / (DaysPerSeason * SeasonNames.Length) + 1;
        var season = SeasonNames[day / DaysPerSeason % SeasonNames.Length];
        return $"第{year}年 {season}{day % DaysPerSeason + 1}日";
    }

    /// <summary>压力注入的玩家句池：短、日常、不带角色特征（流水用）。</summary>
    private static readonly string[] StressPlayerLines = new[]
    {
        "早上好，今天天气不错。",
        "我刚从矿洞回来。",
        "农场那边的活儿忙完了。",
        "今天镇上挺热闹的。",
        "我带了点东西给你。",
        "最近睡得还好吗？",
        "我在河边坐了一会儿。",
        "今年的收成还不错。",
        "刚才在森林里转了转。",
        "你最近在忙什么？",
        "我得去一趟杂货店。",
        "明天有空的话一起走走？",
    };

    /// <summary>压力注入的 NPC 句池：同样刻意通用，避免替角色编造性格。</summary>
    private static readonly string[] StressNpcLines = new[]
    {
        "嗯，还行。你呢？",
        "今天风挺大的。",
        "谢谢你上次帮我。",
        "我最近在忙点自己的事。",
        "这个季节总让人犯困。",
        "你也别太累了。",
        "等忙完这阵子再说吧。",
        "我记住了，回头再说。",
        "听着不错。",
        "难得你过来一趟。",
        "慢慢来，不着急。",
        "我这边都好。",
        "有需要就喊我。",
        "改天再聊。",
        "路上小心。",
    };
}
