from app.services.ytdlp_service import build_format_options


def _fmt(fid, height=None, vcodec="avc1", acodec="mp4a", url=None):
    return {
        "format_id": fid,
        "height": height,
        "vcodec": vcodec,
        "acodec": acodec,
        "url": url,
        "ext": "mp4",
        "filesize": 1000,
    }


def test_tiers_collapse_to_existing_heights():
    info = {
        "formats": [
            _fmt("137", 1080, vcodec="avc1", acodec="none"),   # 仅视频
            _fmt("140", None, vcodec="none", acodec="mp4a"),   # 仅音频
            _fmt("18", 360, url="https://cdn/18.mp4"),          # 渐进式直链
        ]
    }
    opts = build_format_options(info)
    labels = {o["label"] for o in opts}
    assert "1080p" in labels  # 需合并 → server
    assert "360p" in labels   # 渐进式 → direct
    by_label = {o["label"]: o for o in opts}
    assert by_label["1080p"]["direct"] is False
    assert by_label["1080p"]["format_id"] == "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
    assert by_label["360p"]["direct"] is True
    assert by_label["360p"]["format_id"] == "18"


def test_no_video_falls_back_to_best():
    info = {"formats": [_fmt("140", None, vcodec="none", acodec="mp4a")]}
    opts = build_format_options(info)
    assert len(opts) == 1
    assert opts[0]["format_id"] == "best"
