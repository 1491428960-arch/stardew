namespace StardewAI.NPC;

public sealed record FrameRateSample(
    long WindowMilliseconds,
    int RenderedFrames,
    double FramesPerSecond);

/// <summary>
/// Collects a low-overhead rolling frame-rate sample from Display.Rendered.
/// </summary>
public sealed class FrameRateSampler
{
    private readonly Action<FrameRateSample> report;
    private readonly int windowMilliseconds;
    private readonly Func<long> elapsedMilliseconds;
    private long windowStartedAt;
    private int renderedFrames;

    public FrameRateSampler(
        Action<FrameRateSample> report,
        int windowMilliseconds = 5000,
        Func<long>? elapsedMilliseconds = null)
    {
        this.report = report ?? throw new ArgumentNullException(nameof(report));
        if (windowMilliseconds <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(windowMilliseconds));
        }

        this.windowMilliseconds = windowMilliseconds;
        this.elapsedMilliseconds = elapsedMilliseconds ?? GetElapsedMilliseconds;
        windowStartedAt = this.elapsedMilliseconds();
    }

    public void OnRendered()
    {
        renderedFrames++;
        var now = elapsedMilliseconds();
        var elapsed = now - windowStartedAt;
        if (elapsed < windowMilliseconds)
        {
            return;
        }

        var seconds = elapsed / 1000.0;
        report(new FrameRateSample(
            elapsed,
            renderedFrames,
            renderedFrames / seconds));
        windowStartedAt = now;
        renderedFrames = 0;
    }

    private static long GetElapsedMilliseconds() => Environment.TickCount64;
}
