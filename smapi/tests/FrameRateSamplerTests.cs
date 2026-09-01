using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class FrameRateSamplerTests
{
    [Fact]
    public void Reports_fps_after_window_and_resets_the_window()
    {
        var now = 0L;
        var samples = new List<FrameRateSample>();
        var sampler = new FrameRateSampler(
            samples.Add,
            windowMilliseconds: 1000,
            elapsedMilliseconds: () => now);

        for (var index = 0; index < 60; index++)
        {
            sampler.OnRendered();
        }

        Assert.Empty(samples);

        now = 1000;
        sampler.OnRendered();

        var first = Assert.Single(samples);
        Assert.Equal(1000, first.WindowMilliseconds);
        Assert.Equal(61, first.RenderedFrames);
        Assert.Equal(61.0, first.FramesPerSecond, 3);

        now = 1500;
        sampler.OnRendered();
        Assert.Single(samples);

        now = 2000;
        sampler.OnRendered();
        Assert.Equal(2, samples.Count);
        Assert.Equal(2.0, samples[1].FramesPerSecond, 3);
    }

    [Fact]
    public void Rejects_non_positive_window()
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => new FrameRateSampler(_ => { }, windowMilliseconds: 0));
    }
}
