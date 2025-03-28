from flask import Flask, render_template, request, jsonify
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import time  # To track email cooldown
from device_manager import add_device, update_device, get_devices
app = Flask(__name__)

# Dictionary to store last sent time for each error type
last_email_sent = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        signal_power = float(data['signal'])

        # Determine fault type based on signal power
        if -10 >= signal_power > -29:
            detected = "No Fault"
        elif -29 >= signal_power > -33:
            detected = "Fiber Deformation"
            sendMailIfNeeded("Fiber Deformation")
        elif -34 >= signal_power > -40:
            detected = "Attenuation or High Loss"
            sendMailIfNeeded("Attenuation or High Loss")
        else:  # signal_power <= -41
            detected = "Fiber Cut"
            sendMailIfNeeded("Fiber Cut")

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

@app.route('/update_device', methods=['POST'])
def update_device_route():
    data = request.get_json()
    success = update_device(data['device_id'], data['device_name'], data['address'])
    return jsonify({"success": success, "message": "Device updated" if success else "Device not found"})


def sendMailIfNeeded(error_type):
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
    sendMail(error_type)


def sendMail(text):
    """ Function to send an email alert """
    sender_email = 'johncthe1@gmail.com'  # Replace with your email
    receiver_email = 'jcturisangait1996@gmail.com'  # Replace with receiver's email
    subject = 'Fiber Optic Fault Detected'
    body = f"Alert: {text} detected in the fiber optic network."

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
    app.run(debug=True)
