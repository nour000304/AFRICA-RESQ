from event_bus import EventBus


def test_event_and_state_reach_subscriber():
    bus = EventBus()
    channel = bus.subscribe()

    bus.publish_event({"id": 1, "event_type": "fire"})
    bus.publish_state({"tick": 1})

    first = channel.get_nowait()
    second = channel.get_nowait()

    assert '"kind": "event"' in first
    assert '"kind": "state"' in second
    assert '"event_type": "fire"' in first


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    channel = bus.subscribe()

    bus.unsubscribe(channel)
    bus.publish_event({"id": 2})

    assert channel.empty()
    assert bus.subscriber_count() == 0


def test_latest_event_and_state_retained():
    bus = EventBus()

    bus.publish_state({"tick": 7})
    bus.publish_event({"id": 3})

    assert bus.latest_state()["tick"] == 7
    assert bus.latest_event()["id"] == 3


def test_fanout_to_many_subscribers():
    bus = EventBus()
    channels = [bus.subscribe() for _ in range(5)]

    bus.publish_event({"id": 4})

    for channel in channels:
        assert channel.get_nowait() is not None

    assert bus.subscriber_count() == 5