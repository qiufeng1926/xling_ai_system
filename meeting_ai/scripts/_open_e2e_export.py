# -*- coding: utf-8 -*-
from pathlib import Path
import html
import subprocess

desk = Path(r"C:\Users\Administrator\Desktop")
src_md = Path(r"d:\AI\xling_ai_system\meeting_ai\output\exports\E2E_21960f30_meeting_export.md")
src_txt = Path(r"d:\AI\xling_ai_system\meeting_ai\output\exports\E2E_21960f30_transcript.txt")

src = src_md.read_text(encoding="utf-8")
txt = src_txt.read_text(encoding="utf-8")

p1 = desk / "E2E_meeting_export.txt"
p2 = desk / "E2E_meeting_transcript.txt"
p3 = desk / "E2E_meeting_export.html"

p1.write_text(src, encoding="utf-8")
p2.write_text(txt, encoding="utf-8")

escaped = html.escape(src).replace("\n", "<br>\n")
p3.write_text(
    "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
    "<title>E2E Meeting Export</title>"
    "<style>body{font-family:Microsoft YaHei,Segoe UI,sans-serif;"
    "max-width:960px;margin:24px auto;padding:0 16px;line-height:1.7;"
    "background:#fafafa;color:#222}</style></head><body>"
    + escaped
    + "</body></html>",
    encoding="utf-8",
)

print("WROTE", p1)
print("WROTE", p2)
print("WROTE", p3)

subprocess.Popen(["notepad.exe", str(p1)])
subprocess.Popen(["cmd", "/c", "start", "", str(p3)])
subprocess.Popen(["explorer.exe", "/select,", str(p1)])
