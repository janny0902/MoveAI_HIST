from pathlib import Path

p = Path(r"d:\moveAI\backend-ai\space_analyzer.py")
t = p.read_text(encoding="utf-8")
old = "    mime = _guess_image_mime(image_bytes, filename)\n"
new = "    image_bytes, mime = _prepare_image_for_gemini(image_bytes, filename, logs)\n"
if old not in t:
    raise SystemExit("mime line not found")
t = t.replace(old, new, 1)
old2 = (
    "        \"빈 철벽+바닥만 보이면 0~3, 맨 안쪽 소량이면 8~15, \"\n"
    "        \"길이·높이로 중간이면 20~70, 천장·후문 근처까지 가득이면 85~99. \"\n"
)
new2 = (
    "        \"중요: 화면 대부분을 골판지 박스 면이 가리면 85~99 "
    "(빈 바닥이 조금만 보여도 만원에 가깝다). \"\n"
    "        \"빈 철벽+바닥만 보이면 0~3, 맨 안쪽 소량이면 8~15, \"\n"
    "        \"길이·높이로 중간이면 20~70. \"\n"
)
if old2 not in t:
    raise SystemExit("prompt lines not found")
t = t.replace(old2, new2, 1)
p.write_text(t, encoding="utf-8")
print("patched ok")
