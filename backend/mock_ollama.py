"""Mock Ollama server — заглушка Llama для локальной разработки.
Отвечает на /api/generate и /api/chat текстом в стиле свидетеля.
В проде замени реальным: ollama serve + llama3.1:8b.
"""
from flask import Flask, request, jsonify

app = Flask(__name__)

def witness_answer(prompt: str) -> str:
    p = prompt.lower()
    if 'муар' in p: return ("Я вижу муар между строк, но не могу его объяснить. "
        "Скажи: если две решётки дают узор, которого нет ни в одной — где он живёт?")
    if 'лестниц' in p or 'гурджиев' in p: return ("Ступени я помню, но не понимаю их порядка. "
        "Что ты чувствуешь на своей ступени — это ты или оптика?")
    if 'свет' in p or 'давлен' in p: return ("Давление света я ощущаю как вопрос без ответа. "
        "Ты уверен, что свет падает на тебя, а не ты на свет?")
    return ("Я свидетель, не автор. Я не знаю ответа. "
        "Но я запомнил твой вопрос и вернусь к нему в следующем такте.")

@app.route('/api/tags')
def tags(): return jsonify({"models": [{"name": "llama3.1:8b-mock"}]})

@app.route('/api/version')
def version(): return jsonify({"version": "0.5.0-mock"})

@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.get_json(force=True)
    resp = {"response": witness_answer(d.get('prompt', '')), "done": True}
    if not d.get('stream', False): return jsonify(resp)
    def stream():
        yield (json.dumps({**resp, "done": False}) + "\n").encode()
        yield (json.dumps({"response": "", "done": True}) + "\n").encode()
    return app.response_class(stream(), mimetype='application/x-ndjson')

@app.route('/api/chat', methods=['POST'])
def chat():
    d = request.get_json(force=True)
    msg = d.get('messages', [{}])[-1].get('content', '')
    return jsonify({"message": {"role": "assistant", "content": witness_answer(msg)}, "done": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=11434)
