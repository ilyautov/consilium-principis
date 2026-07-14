# VHS: council-clash demo, ILLUSTRATIVE (<11s). vhs scripts/demo/clash.en.tape
# 🟡 arguments are host-generated (not verified); the 🔵 line is checked by the live gate.
Output assets/demo-clash-en.gif
Require python3
Set Shell "bash"
Set FontSize 21
Set Width 1180
Set Height 640
Set Padding 30
Set Theme "Catppuccin Mocha"
Set TypingSpeed 30ms
Hide
Type "export HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999" Enter
Type "consilium() { python3 scripts/demo/clash_demo.py --no-prompt --en; }" Enter
Type "clear" Enter
Show
Sleep 600ms
Type "consilium «I am juggling four directions. Where do I focus?»"
Sleep 500ms
Enter
Sleep 10s
