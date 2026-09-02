from flask import Flask, jsonify  # importa as bibliotecas do Flask

app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({"message": "Olá, mundo!"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)