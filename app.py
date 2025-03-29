from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import time  # To track email cooldown
import json
import bcrypt
import os
from datetime import datetime
from device_manager import add_device, update_device, get_devices
app = Flask(__name__)

# Dictionary to store last sent time for each error type
last_email_sent = {}

JSON_FILE = "devices.json"
EMAIL_LOG_FILE = "email_log.json"

# Ensure JSON file exists
if not os.path.exists(JSON_FILE):
    with open(JSON_FILE, "w") as f:
        json.dump([], f)

# Ensure email log file exists
if not os.path.exists(EMAIL_LOG_FILE):
    with open(EMAIL_LOG_FILE, "w") as f:
        json.dump({}, f)


def read_json():
    """ Read devices from JSON file """
    with open(JSON_FILE, "r") as f:
        return json.load(f)


def write_json(data):
    """ Write devices to JSON file """
    with open(JSON_FILE, "w") as f:
        json.dump(data, f, indent=4)


@app.route('/')
def index():    
    if "user" in session:
        return render_template("index.html", user=session["user"])
    return redirect(url_for("login"))

@app.route('/home')
def home():    
    if "user" in session:
        return render_template("index.html", user=session["user"])
    return redirect(url_for("login"))


app.secret_key = "supersecretkey"

USERS_FILE = "users.json"

# Load users from JSON file
def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r") as file:
        return json.load(file)

# Save users to JSON file
def save_users(users):
    with open(USERS_FILE, "w") as file:
        json.dump(users, file, indent=4)



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"].encode("utf-8")
        users = load_users()

        for user in users:
            if user["email"] == email and bcrypt.checkpw(password, user["password"].encode("utf-8")):
                session["user"] = user["name"]
                return redirect(url_for("home"))
        
        return "Invalid credentials!", 401
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"].encode("utf-8")
        hashed_password = bcrypt.hashpw(password, bcrypt.gensalt()).decode("utf-8")

        users = load_users()
        users.append({"name": name, "email": email, "password": hashed_password})
        save_users(users)

        return redirect(url_for("login"))
    
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))



@app.route('/history')
def history():
    return render_template('history.html')


@app.route('/analytics')
def analytics():
    return render_template('analytic.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        signal_power = float(data['signal'])
        attenuationx = float(data['attenuation'])
        distance = int(data['distance'])

        # Determine fault type based on signal power
        if 0 >= signal_power > -29:
            detected = "No Fault"
        elif -29 >= signal_power > -33:
            detected = "Fiber Deformation"
            sendMailIfNeeded("Fiber Deformation", attenuationx, distance, signal_power)
        elif -34 >= signal_power > -40:
            detected = "Attenuation or High Loss"
            sendMailIfNeeded("Attenuation or High Loss", attenuationx, distance, signal_power)
        else:  # signal_power <= -41
            detected = "Fiber Cut"
            sendMailIfNeeded("Fiber Cut", attenuationx, distance, signal_power)

        result = {
            "detected": detected,
            "probabilities": {
                "No Fault": 100 if detected == "No Fault" else 0,
                "Fiber Deformation": 100 if detected == "Fiber Deformation" else 0,
                "High Loss": 100 if detected == "Attenuation or High Loss" else 0,
                "Fiber Cut": 100 if detected == "Fiber Cut" else 0,
            },
            "interpretation": f"Detected issue: {detected}."
        }

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 400

def read_json1():
    try:
        with open('history.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return []

# Function to write data to the history.json file
def write_json1(data):
    with open('history.json', 'w') as file:
        json.dump(data, file, indent=4)



@app.route('/get_history', methods=['GET'])
def get_history():
    try:
        with open('history.json', 'r') as file:
            history_data = json.load(file)
        history_data.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d %H:%M:%S'), reverse=True)
        return jsonify(history_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def calculate_attenuation(scaled_fiber_val):
    # Define the attenuation based on the scaled_fiber_val
    if 0 >= scaled_fiber_val > -29:
        # No Fault
        attenuation = 0  # No attenuation
    elif -29 >= scaled_fiber_val > -33:
        # Fiber Deformation
        attenuation = 1 + (scaled_fiber_val + 29) * (3 - 1) / (-33 + 29)  # Interpolate between 1 dB and 3 dB
    elif -34 >= scaled_fiber_val > -40:
        # Attenuation or High Loss
        attenuation = 4 + (scaled_fiber_val + 34) * (7 - 4) / (-40 + 34)  # Interpolate between 4 dB and 7 dB
    else:
        # Fiber Cut
        attenuation = 10  # Severe attenuation for fiber cut
    
    return round(attenuation, 2)




@app.route("/get_history_data", methods=["GET"])
def get_history_data():
    """Handle GET request and return all history data"""
    try:
        with open('history.json', 'r') as file:
            history_data = json.load(file)
        # Sort the data by date in descending order
        # history_data.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d %H:%M:%S'), reverse=True)
        
        return jsonify(history_data)  # Return the data as JSON
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route("/getdata", methods=["GET"])
def get_data():
    """Handle GET request and store incoming data in the history.json file"""
    # Get the query parameters
    device_id = request.args.get('device_id')
    fiber_val = request.args.get('fiber_value')

    # Validate the presence of required query parameters
    if not device_id or not fiber_val:
        return jsonify({"message": "Missing required parameters!"}), 400
    
    # Read the existing devices from the JSON file
    devices = read_json()
    
    # Check if the device is registered
    device_found = False
    for device in devices:
        if device["device_id"] == device_id:
            device_found = True
            break
    
    if not device_found:
        return jsonify({"message": "Device not registered!"}), 400

    # Create a new device entry based on the query parameters
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    
    new_va = int(fiber_val)
    if new_va < 10:
        new_va = 10
    elif new_va > 650:
        new_va = 650

    # Scale LDR value (10-650) to the desired range (-0 to -50)
    # scaled_fiber_val = ((new_va - 10) * (-50 - 0)) / (650 - 10) + 0
    # Normalize the LDR value (10-650) to a value between 0 and 1
    normalized_value = (new_va - 10) / (650 - 10)

    # Reverse the scale to map the value to the range -0 to -50
    scaled_fiber_val = (1 - normalized_value) * -50

    attenuation = calculate_attenuation(scaled_fiber_val)
    
    if 0 >= scaled_fiber_val > -29:
        detected = "No Fault"
    elif -29 >= scaled_fiber_val > -33:
        detected = "Fiber Deformation"
        sendMailIfNeeded("Fiber Deformation", attenuation, "4000", scaled_fiber_val)
    elif -34 >= scaled_fiber_val > -40:
        detected = "Attenuation or High Loss"
        sendMailIfNeeded("Attenuation or High Loss", attenuation, "4000", scaled_fiber_val)
    else:  # scaled_fiber_val <= -41
        detected = "Fiber Cut"
        sendMailIfNeeded("Fiber Cut", attenuation, "4000", scaled_fiber_val)
    
    new_device = {
        "device_id": device_id,
        "fiber_val": scaled_fiber_val,  # Ensure fiber_val is an integer
        "date" : current_time,
        "details" : detected,
        "attenuation" : attenuation,
        "distance" : 200,
    }

    # Read existing data from history.json
    devices = read_json1()

    # Append the new device data to the list
    devices.append(new_device)

    # Write the updated data back to history.json
    write_json1(devices)

    # Return a success message
    return jsonify({"message": "Data added successfully!"}), 200

@app.route('/devices')
def devices_page():
    return render_template('devices.html')

@app.route('/get_devices', methods=['GET'])
def get_devices_route():
    return jsonify(get_devices())

@app.route('/add_device', methods=['POST'])
def add_device_route():
    data = request.get_json()
    success = add_device(data['device_id'], data['device_name'], data['address'])
    return jsonify({"success": success, "message": "Device added" if success else "Device ID already exists"})


@app.route("/edit_device", methods=["POST"])
def edit_device():
    """Edit an existing device."""
    data = request.get_json()  # Get the incoming JSON data
    
    # Check if the necessary fields are present in the request data
    if not all(key in data for key in ["device_id", "device_name", "address"]):
        return jsonify({"message": "Missing required fields: device_id, device_name, address"}), 400

    # Read the existing devices from the JSON file
    devices = read_json()
    
    # Find the device by device_id
    for device in devices:
        if device["device_id"] == data["device_id"]:
            # Update the device's name and address
            device["device_name"] = data["device_name"]
            device["address"] = data["address"]

            # Write the updated list of devices back to the JSON file
            write_json(devices)
            
            # Return success response
            return jsonify({"message": "Device updated successfully!"}), 200

    # If the device ID is not found, return an error message
    return jsonify({"message": "Device not found!"}), 404



@app.route("/update_device", methods=["POST"])
def update_device():
    """ Update existing device """
    data = request.get_json()
    devices = read_json()

    for device in devices:
        if device["device_id"] == data["device_id"]:
            device["device_name"] = data["device_name"]
            device["address"] = data["address"]
            write_json(devices)
            return jsonify({"message": "Device updated successfully!"})

    return jsonify({"message": "Device not found!"}), 404


@app.route("/delete_device", methods=["POST"])
def delete_device():
    """ Delete a device """
    data = request.get_json()
    devices = read_json()

    devices = [device for device in devices if device["device_id"] != data["device_id"]]
    write_json(devices)

    return jsonify({"message": "Device deleted successfully!"})

def sendMailIfNeeded(error_type, ettenua, distan, signal_power):
    """ Sends an email only if 2 minutes have passed since the last email for this error. """
    global last_email_sent
    current_time = time.time()

    # Check if an email was sent before and if 2 minutes have passed
    if error_type in last_email_sent:
        time_since_last_email = current_time - last_email_sent[error_type]
        if time_since_last_email < 20:  # 120 seconds = 2 minutes
            print(f"Skipping email for {error_type}, last email sent {time_since_last_email:.1f} seconds ago.")
            return

    # Update last sent time and send the email
    last_email_sent[error_type] = current_time
    sendMail(error_type, ettenua, distan, signal_power)


def sendMail(text,atten,distance,signal_power):
    """ Function to send an email alert """
    sender_email = 'johncthe1@gmail.com'  # Replace with your email
    receiver_email = 'jcturisangait1996@gmail.com;jadokanamugire@gmail.com'  # Replace with receiver's email
    subject = 'Fiber Fault identification'
    body = f"Alert: {text} detected in the fiber optic network, with signal power of {signal_power}, attenuation of {atten} at {distance} distance"

    password = 'lewdmjrjmwkfdgpb'  # Replace with your actual email password or App Password

    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = receiver_email
    message['Subject'] = subject
    message.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        print("Email sent successfully!")

    except Exception as e:
        print(f"Failed to send email: {e}")

    finally:
        server.quit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

