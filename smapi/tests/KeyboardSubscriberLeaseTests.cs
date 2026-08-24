using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class KeyboardSubscriberLeaseTests
{
    [Fact]
    public void AcquireStoresPreviousSubscriberBeforeReplacingIt()
    {
        var previous = new object();
        var input = new object();
        object? current = previous;
        var lease = new KeyboardSubscriberLease<object>(
            () => current,
            value => current = value);

        lease.Acquire(input);

        Assert.Same(input, current);
        lease.Release();

        Assert.Same(previous, current);
    }

    [Fact]
    public void ReleaseDoesNotOverwriteAThirdPartySubscriber()
    {
        var previous = new object();
        var input = new object();
        var thirdParty = new object();
        object? current = previous;
        var lease = new KeyboardSubscriberLease<object>(
            () => current,
            value => current = value);

        lease.Acquire(input);
        current = thirdParty;
        lease.Release();

        Assert.Same(thirdParty, current);
    }

    [Fact]
    public void SuspendAndResumeOnlyChangeTheSubscriberOwnedByTheLease()
    {
        var previous = new object();
        var input = new object();
        object? current = previous;
        var lease = new KeyboardSubscriberLease<object>(
            () => current,
            value => current = value);

        lease.Acquire(input);
        lease.Suspend();
        lease.Suspend();

        Assert.Null(current);

        lease.Resume();
        lease.Resume();

        Assert.Same(input, current);
    }

    [Fact]
    public void ReleaseIsIdempotentAndRestoresPreviousSubscriber()
    {
        var previous = new object();
        var input = new object();
        object? current = previous;
        var lease = new KeyboardSubscriberLease<object>(
            () => current,
            value => current = value);

        lease.Acquire(input);
        lease.Release();
        lease.Release();

        Assert.Same(previous, current);
    }
}
