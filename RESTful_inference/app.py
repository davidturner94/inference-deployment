from flask import Flask, jsonify, request, Markup, redirect, abort
import torch
from time import perf_counter_ns
import time
import tools.utils as utils
from tools.utils import get_top5, IMAGENET_MODELS
import torchvision.models as models
import torchvision.transforms as transforms
import tools.torchsummary as torchsummary
from PIL import Image
from io import BytesIO
from pynvml.smi import nvidia_smi
import json

app = Flask(__name__)

net = models.resnet18(pretrained=True)
net.name = "resent18"
net.eval()
net.to(utils.DEVICE)
net_info = torchsummary.summary(net, (3, 224, 224))

CUDA_AVAILABLE = True if utils.DEVICE.type == 'cuda' else False

if CUDA_AVAILABLE:
    nvsmi = nvidia_smi.getInstance()

    

@app.route("/")
def index():
    """
    :return: json response
    :rtype: json object
    """
    response = {
        "status": "All Good.",
        "device": utils.DEVICE.type,
        "current_model": net.name
    }
    return jsonify(response)


@app.route("/inference", methods=["POST"])
def inference():
    """
    Method for inference on a provided image

    This method takes a json request containing an image and the model to test
    and returns json data containing the predicted result and some meta data
    relating to inference time and confidence score.


    """

    request_recieved = time.time()
    
    if request.data:
        json_req = json.loads(request.data.decode('utf-8'))
        im_tensor = torch.FloatTensor(json_req['image'])
        
    if request.files:
        # Convery bytes to image
        # print(request.files["files"])
        im = Image.open(BytesIO(request.files['files'].read()))

        # image preprocessing: convert to tensor and add dimension to mimick batch
        im_tensor = transforms.ToTensor()(im)

    im_tensor = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                     std=[0.229, 0.224, 0.225])(im_tensor)

    data = im_tensor.unsqueeze(0)
    data = data.to(utils.DEVICE)

    # # run inference
    perf_start = time.time()
    

    # # inference here
    (top5_values, top5_indicies), raw = get_top5(net, data)

    if CUDA_AVAILABLE:
        post_inf_power = nvsmi.DeviceQuery('power.draw, utilization.gpu')

    perf_end = time.time()

    # return results as a json
    return jsonify({
        "result": {
            "inference_time_ms": perf_end-perf_start,
            "prediction_raw": raw[0].tolist(),
        },
        "meta": {
            "device": utils.DEVICE.type,
            "cuda_info": post_inf_power if CUDA_AVAILABLE else None ,
            "model": {
                "name": net.name,
                "size_in_MB": net_info['total_size'],
                "no_params": net_info['total_params'],
            },
            "time_response_sent": time.time(),  # This is to enable calculation of latency
            "time_request_recieved": request_recieved,
        }
    })


@ app.route("/model")
def model():
    summary = torchsummary.summary(net, (3, 224, 224))
    summary['model_name'] = net.name
    return jsonify(summary)

@app.route("/avail_models")
def avail_models():
    return jsonify({"available_models": [x for x in IMAGENET_MODELS.keys()]})

@app.route("/set_model/<model>", methods=["POST"])
def change_model(model):
    if request.json.get('api_key') != 'password':
        abort(400)
    if model in IMAGENET_MODELS.keys():
        global net
        global net_info
        net = IMAGENET_MODELS[model](pretrained=True)
        net.name = model
        net.eval()
        net.to(utils.DEVICE)
        net_info = torchsummary.summary(net, (3, 224, 224))
        net_info['model_name'] = net.name
        return jsonify(net_info) 
    else:
        return jsonify({"available_models": [x for x in IMAGENET_MODELS.keys()]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
