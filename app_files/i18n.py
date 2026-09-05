"""User-facing speech, independent of the language of monitored replies."""

MESSAGES = {
    "zh": {
        "greeting": "GPT Monitor 开始监听",
        "copied": "已复制",
        "copy_empty": "没有找到可复制的回复",
        "attention": "需要你处理",
        "permission": "请在系统设置的输入监控中允许 GPT Monitor",
        "voice_test": "GPT Monitor 本地语音测试完成",
        "reply_start": "正在回复",
    },
    "en": {
        "greeting": "GPT Monitor is listening",
        "copied": "Copied",
        "copy_empty": "No reply available to copy",
        "attention": "Your attention is needed",
        "permission": "Please allow GPT Monitor in System Settings, Privacy and Security, Input Monitoring",
        "voice_test": "GPT Monitor English voice test complete",
        "reply_start": "A reply is being written",
    },
}


def message(config, key: str) -> str:
    try:
        language = config["language"]
    except KeyError:
        language = "zh"
    return MESSAGES["en" if language.lower().startswith("en") else "zh"][key]
