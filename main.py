from fastapi import FastAPI, File, UploadFile
import uvicorn
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image
from PIL import Image
import io

app = FastAPI()

# Load Keras model
model = load_model("./model/waste_model.keras")

# Waste labels (adjust to match your training order)
labels = ['plastic', 'paper', 'organic', 'metal', 'glass']

@app.post("/classify")
async def classify(file: UploadFile = File(...)):
    # Read uploaded image
    image_bytes = await file.read()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    # Preprocess image (resize to your model input size, e.g., 224x224)
    img = img.resize((224, 224))
    img_array = image.img_to_array(img)
    img_array = np.expand_dims(img_array, axis=0) / 255.0  # normalize to [0,1]
    
    # Predict
    predictions = model.predict(img_array)
    predicted_class = np.argmax(predictions[0])
    label = labels[predicted_class]

    return {"label": label}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
