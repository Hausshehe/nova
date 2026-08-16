import subprocess

MODEL = "/data/data/com.termux/files/home/.cache/huggingface/hub/models--Qwen--Qwen3-4B-GGUF/snapshots/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf"
PROMPT_FILE = "/data/data/com.termux/files/home/infoney/infoney_prompt.txt"
LLAMA = "/data/data/com.termux/files/home/infoney/llama.cpp/build/bin/llama-cli"

question = "Hello Infoney, how are you?"

result = subprocess.run(
    [
        LLAMA,
        "-m", MODEL,
        "--system-prompt-file", PROMPT_FILE,
        "-t", "4",
        "-c", "4096",
        "-fa", "auto",
        "-p", question
    ],
    capture_output=True,
    text=True
)

print(result.stdout)
