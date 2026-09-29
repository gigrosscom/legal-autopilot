from fastapi.testclient import TestClient


def new_user(client: TestClient, **body) -> dict:
    r = client.post("/v1/users", json={"language": "ru", **body})
    assert r.status_code == 200
    return r.json()


def test_invite_link_counts_new_people_and_channels(ctx):
    client = ctx.client
    alice = new_user(client, src="tiktok")
    h = {"Authorization": f"Bearer {alice['token']}"}
    ref = client.get("/v1/referral", headers=h).json()
    assert ref["link"].endswith(f"?ref={ref['code']}") and ref["invited"] == 0
    assert client.get("/v1/referral", headers=h).json()["code"] == ref["code"]  # stable

    new_user(client, ref=ref["code"].upper())
    new_user(client, ref=ref["code"], src="whatsapp")
    new_user(client, ref="nosuchcode")
    assert client.get("/v1/referral", headers=h).json()["invited"] == 2

    m = client.get("/v1/admin/metrics", headers={"X-Admin-Token": "adm"}).json()["referral"]
    assert m["referred_users"] == 2 and m["inviters"] == 1
    assert m["sources"]["tiktok"] == 1 and m["sources"]["referral"] == 1 and m["sources"]["whatsapp"] == 1
    assert m["k_factor"] == round(2 / 2, 3)
