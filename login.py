import requests

ip = input('push link button and enter bridge ip:')

req_data = {
    "devicetype":"hueartnet#pc",
    "generateclientkey":True
}

r = requests.post(f'http://{ip}/api', json=req_data)

print(r.json())