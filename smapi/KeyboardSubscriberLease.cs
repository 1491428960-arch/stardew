namespace StardewAI.NPC;

/// <summary>
/// Owns a nullable keyboard subscriber without overwriting a subscriber that
/// another menu installed after this lease was acquired.
/// </summary>
public sealed class KeyboardSubscriberLease<TSubscriber>
    where TSubscriber : class
{
    private readonly Func<TSubscriber?> getSubscriber;
    private readonly Action<TSubscriber?> setSubscriber;
    private TSubscriber? previousSubscriber;
    private TSubscriber? acquiredSubscriber;
    private bool acquired;

    public KeyboardSubscriberLease(
        Func<TSubscriber?> getSubscriber,
        Action<TSubscriber?> setSubscriber)
    {
        this.getSubscriber = getSubscriber ?? throw new ArgumentNullException(nameof(getSubscriber));
        this.setSubscriber = setSubscriber ?? throw new ArgumentNullException(nameof(setSubscriber));
    }

    public void Acquire(TSubscriber subscriber)
    {
        ArgumentNullException.ThrowIfNull(subscriber);
        if (acquired)
        {
            throw new InvalidOperationException("键盘订阅 lease 已经获取。 ");
        }

        previousSubscriber = getSubscriber();
        acquiredSubscriber = subscriber;
        acquired = true;
        setSubscriber(subscriber);
    }

    public void Suspend()
    {
        if (acquired && ReferenceEquals(getSubscriber(), acquiredSubscriber))
        {
            setSubscriber(null);
        }
    }

    public void Resume()
    {
        if (acquired && getSubscriber() is null)
        {
            setSubscriber(acquiredSubscriber);
        }
    }

    public void Release()
    {
        if (!acquired)
        {
            return;
        }

        if (ReferenceEquals(getSubscriber(), acquiredSubscriber))
        {
            setSubscriber(previousSubscriber);
        }

        previousSubscriber = null;
        acquiredSubscriber = null;
        acquired = false;
    }
}
