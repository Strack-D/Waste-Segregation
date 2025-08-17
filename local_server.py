from flask import Flask, request, jsonify
from keras.models import load_model
from keras.preprocessing import image
import numpy as np
import io

app = Flask(__name__)
model = load_model("./model/waste_model.keras")  # Update path to your model

@app.route('/classify', methods=['POST'])
def classify():
    img = image.load_img(io.BytesIO(request.data), target_size=(224, 224))
    img_array = image.img_to_array(img) / 255.0
    img_array = np.expand_dims(img_array, axis=0)

    prediction = model.predict(img_array)
    label = np.argmax(prediction[0])
    return jsonify({"label": int(label)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)  # Accessible on network