from app.runtime.provider_process_pool import ProviderProcessPool


def test_provider_process_pool_reuses_existing_handle() -> None:
    pool = ProviderProcessPool()
    calls = 0

    def factory() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"calls": calls}

    first = pool.get_or_create(key="codex:gpt-5.4", factory=factory)
    second = pool.get_or_create(key="codex:gpt-5.4", factory=factory)

    assert first is second
    assert first.payload == {"calls": 1}
    assert calls == 1


def test_provider_process_pool_invalidate_drops_single_handle() -> None:
    pool = ProviderProcessPool()
    pool.get_or_create(key="codex:gpt-5.4", factory=lambda: {"ok": 1})
    pool.invalidate("codex:gpt-5.4")

    assert pool.size() == 0


def test_provider_process_pool_clear_drops_all_handles() -> None:
    pool = ProviderProcessPool()
    pool.get_or_create(key="codex:gpt-5.4", factory=lambda: {"ok": 1})
    pool.get_or_create(key="gemini:gemini-2.5-flash", factory=lambda: {"ok": 2})

    pool.clear()

    assert pool.size() == 0
