# VHS: демо C «спросил по-русски, 🔵 по англ. тексту» (<10с). vhs scripts/demo/crosslingual.tape
# 🔵-сверку якорной строки считает живой гейт (crosslingual_demo.py); перевод — работа совета.
Output assets/demo-crosslingual.gif
Require python3
Set Shell "bash"
Set FontSize 22
Set Width 1120
Set Height 620
Set Padding 30
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Hide
Type "export HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999" Enter
Type "consilium() { python3 scripts/demo/crosslingual_demo.py --no-prompt; }" Enter
Type "clear" Enter
Show
Sleep 600ms
Type "consilium ask"
Sleep 400ms
Enter
Sleep 8s
