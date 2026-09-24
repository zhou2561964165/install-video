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
    by_label = {o["label"]: o for o in opts}
    assert "1080p 最佳 (视频+音频合并)" in by_label  # 需合并 → server
    assert "360p MP4 (1KB)" in by_label            # 渐进式 → direct
    assert by_label["1080p 最佳 (视频+音频合并)"]["direct"] is False
    assert by_label["1080p 最佳 (视频+音频合并)"]["format_id"] == "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
    assert by_label["1080p 最佳 (视频+音频合并)"]["has_audio"] is True
    assert by_label["360p MP4 (1KB)"]["direct"] is True
    assert by_label["360p MP4 (1KB)"]["format_id"] == "18"
    assert by_label["360p MP4 (1KB)"]["has_audio"] is True


def test_no_video_falls_back_to_best():
    info = {"formats": [_fmt("140", None, vcodec="none", acodec="mp4a")]}
    opts = build_format_options(info)
    assert len(opts) == 1
    assert opts[0]["format_id"] == "best"
    assert opts[0]["label"] == "最佳"


def test_sub_1080_without_progressive_is_skipped():
    # 低于 1080p 的档位无渐进式直链时，不回退 ffmpeg 合并，而是跳过该档
    info = {
        "formats": [
            _fmt("137", 1080, vcodec="avc1", acodec="none"),   # 仅视频 1080
            _fmt("140", None, vcodec="none", acodec="mp4a"),   # 仅音频
            _fmt("135", 480, vcodec="avc1", acodec="none"),    # 仅视频 480（无渐进式）
        ]
    }
    opts = build_format_options(info)
    labels = [o["label"] for o in opts]
    assert "1080p 最佳 (视频+音频合并)" in labels
    assert not any("480" in l for l in labels)
