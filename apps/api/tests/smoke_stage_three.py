"""Stage-three live smoke test against the Docker API and configured VLM."""

import asyncio
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

API = "http://localhost:8000/api/v1"
FIXTURE = Path(".data/stage3-ding-label.png")
UNKNOWN_FIXTURE = Path(".data/stage3-unknown-glyph.png")


def create_label_fixture() -> Path:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1400, 800), "#f4ead6")
    draw = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if not font_path.exists():
        font_path = Path("C:/Windows/Fonts/simhei.ttf")
    title = ImageFont.truetype(str(font_path), 92)
    body = ImageFont.truetype(str(font_path), 52)
    draw.text((90, 80), "云字展签", font=title, fill="#241a15")
    draw.text((90, 245), "时代：商代晚期", font=body, fill="#3a2b22")
    draw.text((90, 350), "用途：礼仪与祭祀", font=body, fill="#3a2b22")
    draw.text((90, 455), "目标字：云", font=body, fill="#3a2b22")
    draw.text((90, 560), "展签主题：器物、礼制与文化", font=body, fill="#3a2b22")
    image.save(FIXTURE)
    return FIXTURE


def create_unknown_fixture() -> Path:
    UNKNOWN_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (900, 700), "#f4ead6")
    draw = ImageDraw.Draw(image)
    draw.line([(220, 150), (450, 80), (680, 150)], fill="#241a15", width=35)
    draw.line([(450, 85), (450, 580)], fill="#241a15", width=35)
    draw.ellipse((260, 220, 640, 520), outline="#241a15", width=35)
    draw.line([(300, 580), (600, 580)], fill="#241a15", width=35)
    image.save(UNKNOWN_FIXTURE)
    return UNKNOWN_FIXTURE


async def main() -> None:
    fixture = create_label_fixture()
    unknown_fixture = create_unknown_fixture()
    async with httpx.AsyncClient(timeout=90) as client:
        for _ in range(30):
            try:
                health = await client.get(f"{API}/health")
                if health.is_success:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError("API did not become healthy")
        with fixture.open("rb") as handle:
            response = await client.post(
                f"{API}/assets",
                files={"file": (fixture.name, handle, "image/png")},
            )
        response.raise_for_status()
        asset = response.json()
        assert asset["status"] == "completed", asset
        assert "云" in asset["analysis"]["target_characters"], asset["analysis"]
        assert asset["analysis"]["requires_target_confirmation"] is False
        assert asset["analysis"]["fallback_used"] is False, asset["analysis"]

        response = await client.post(
            f"{API}/tasks",
            json={
                "raw_input": "根据上传的博物馆展签，为小学六年级制作 4 分钟讲解。",
                "asset_ids": [asset["id"]],
            },
        )
        response.raise_for_status()
        task = response.json()
        assert task["spec"]["target_characters"] == ["云"], task["spec"]
        assert task["input_asset_ids"] == [asset["id"]]

        with unknown_fixture.open("rb") as handle:
            response = await client.post(
                f"{API}/assets",
                files={"file": (unknown_fixture.name, handle, "image/png")},
            )
        response.raise_for_status()
        unknown = response.json()
        assert unknown["analysis"]["target_characters"] == [], unknown["analysis"]
        assert unknown["analysis"]["requires_target_confirmation"] is True
        print(
            "stage-three smoke passed:",
            asset["analysis"]["model"],
            task["id"],
        )


if __name__ == "__main__":
    asyncio.run(main())
