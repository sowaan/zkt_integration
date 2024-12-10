# Copyright (c) 2024, Sowaan and contributors
# For license information, please see license.txt
import requests
import json

import frappe
from frappe.model.document import Document
from datetime import datetime, timedelta


class ZKTSetting(Document):
	@frappe.whitelist()
	def get_token(self):
		try:
			tokenApi = f'''http://{self.host_ip}:{self.port}/api-token-auth/'''
			headers = {"Content-Type": "application/json"}
			response = requests.get(tokenApi, headers=headers)
			token = json.loads(response.text).get("token")
			frappe.db.set_value("ZKT Setting", self.name, "token", token)
		except requests.exceptions.RequestException as e:
			frappe.log_error(message=str(e), title="ZKT Token API Error")
			frappe.throw(f"Error while fetching token: {e}")
		except Exception as e:
			frappe.log_error(message=str(e), title="Unexpected Error in get_token")
			frappe.throw("An unexpected error occurred.")
	

@frappe.whitelist()
def get_zkt_log_scheduler():
	try:
		setting_list = frappe.get_all("ZKT Setting", fields=["*"])
		for setting in setting_list:
			get_zkt_log(setting)
	except Exception as e:
		frappe.log_error(message=str(e), title="ZKT Log Scheduler Error")


@frappe.whitelist()
def get_zkt_log(setting):
	try:
		if isinstance(setting, str):
			setting = json.loads(setting)
		baseUrl = f'''http://{setting.get("host_ip")}:{setting.get("port")}/'''

		filters = []
		if setting.get("device_serial_number"):
			filters.append(f"terminal_sn={setting.get('device_serial_number')}")
		if setting.get("data_limit"):
			filters.append(f"limit={setting.get('data_limit')}")
		if setting.get("employee_code"):
			filters.append(f"emp_code={setting.get('employee_code')}")
		if setting.get("start_time"):
			filters.append(f"start_time={setting.get('start_time')}")
		if setting.get("end_time"):
			filters.append(f"end_time={setting.get('end_time')}")

		tokenApi = f'''{baseUrl}api-token-auth/'''

		headers = {"Content-Type": "application/json"}

		if setting.get("token"):
			headers["Authorization"] = f'''Token {setting.get("token")}'''
		else:
			response = requests.get(tokenApi, headers=headers)
			token = json.loads(response.text).get("token")
			if not token:
				frappe.throw("Failed to fetch token from API.")
			frappe.db.set_value("ZKT Setting", setting.get("name"), "token", token)
			headers["Authorization"] = f'''Token {token}'''

		transectionApi = f'''{baseUrl}api/{setting.get("end_point")}/?'''
		if filters:
			transectionApi += "&".join(filters)

		response = requests.get(transectionApi, headers=headers)
		data = json.loads(response.text).get("data")
		if not data:
			frappe.log_error("No data retrieved from transaction API", title="ZKT Log Warning")
			return

		last_punch_time = ""
		for d in data:
			last_punch_time = d.get("punch_time")
			employee = get_employee(d.get("emp_code"))
			if not employee:
				frappe.log_error(f"Employee not found for att_id {d.get('emp_code')}", title="Employee Not Found")
				continue
			checklog = frappe.db.exists("Employee Checkin", {"employee": employee.get("name"), "time": d.get("punch_time")})
			if not checklog:
				frappe.get_doc({
					"doctype": "Employee Checkin",
					"employee": employee.get("name"),
					"time": d.get("punch_time"),
					"device_id": d.get("terminal_sn"),
					"log_type": "IN" if d.get("punch_state") in ['0', '2', '4'] else "OUT",
				}).insert()
		if last_punch_time:
			last_punch_datetime = datetime.strptime(last_punch_time, "%Y-%m-%d %H:%M:%S")
			new_end_time = last_punch_datetime + timedelta(days=1)
			new_end_time_str = new_end_time.strftime("%Y-%m-%d %H:%M:%S")
			
			frappe.db.set_value("ZKT Setting", setting.get("name"), "start_time", last_punch_time)
			frappe.db.set_value("ZKT Setting", setting.get("name"), "end_time", new_end_time_str)	
	except requests.exceptions.RequestException as e:
		frappe.log_error(message=str(e), title="ZKT API Request Error")
	except Exception as e:
		frappe.log_error(message=str(e), title="Unexpected Error in get_zkt_log")


def get_employee(att_id):
	employee = frappe.get_last_doc("Employee", filters={"attendance_device_id": att_id})
	if employee:
		return employee
	else:
		return None
