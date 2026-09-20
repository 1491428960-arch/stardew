namespace StardewAI.NPC;

public sealed record GroupInvitationTemplate(
    string TemplateId,
    string Title,
    string Topic,
    string Guidance,
    string Source,
    IReadOnlyList<string> RequiredParticipants);

public static class GroupInvitationTemplates
{
    public static IReadOnlyList<GroupInvitationTemplate> All { get; } = new[]
    {
        new GroupInvitationTemplate(
            "neutral-public-topic",
            "聊聊最近的公共小事",
            "最近在镇上、农场或附近地区发生的公共小事",
            "把它当作开放的讨论方向，让每名 NPC 只从自己的经历和看法回应。",
            "periodic",
            Array.Empty<string>()),
        new GroupInvitationTemplate(
            "mineral-and-mystery",
            "奇怪的矿石",
            "一块奇怪的矿石和矿洞传闻",
            "Abigail 和 Emily 可以从各自的兴趣与直觉出发讨论，不把传闻直接当成已确认事实。",
            "periodic",
            new[] { "Abigail", "Emily" }),
        new GroupInvitationTemplate(
            "research-follow-up",
            "研究观察",
            "一项值得继续观察的研究现象",
            "Wizard 和 Sophia 可以分享各自知道的部分，只讨论现有信息，不安排未来会面或实验时间。",
            "story",
            new[] { "Wizard", "Sophia" }),
        new GroupInvitationTemplate(
            "adventure-trio",
            "下矿前的准备",
            "一次下矿计划里各自的准备与顾虑",
            "Abigail、Sebastian 和 Maru 可以从各自的经验出发聊聊准备与担心，"
            + "只讨论现有信息，不安排具体时间或地点。",
            "periodic",
            new[] { "Abigail", "Sebastian", "Maru" }),
        new GroupInvitationTemplate(
            "seasonal-chores",
            "换季的琐事",
            "换季时镇上和农场里忙的那些事",
            "Robin、Marnie 和 Caroline 可以聊聊各自手头的活计，"
            + "不替别人安排日程，也不承诺具体帮忙的时间。",
            "periodic",
            new[] { "Robin", "Marnie", "Caroline" }),
        new GroupInvitationTemplate(
            "social-perspective",
            "不同的看法",
            "玩家与其他人相处时的不同看法",
            "Alex 和 Sebastian 只表达各自的感受与观点，不替对方发言，也不直接宣布关系结果。",
            "relationship",
            new[] { "Alex", "Sebastian" }),
    };
}
