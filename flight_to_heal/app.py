import random
import sys
import mysql.connector
from flask import Flask, request, jsonify, session, render_template
from datetime import timedelta


class GameData:
    DB_CONFIG = {
        'host': 'localhost',
        'port': 3306,
        'database': 'flight_to_heal',
        'user': 'root',
        'password': 'DohaLife12*',
        'autocommit': True
    }

    MAXIMUM_TIME_MINUTES = 1440
    START_HEALTH = 75.0
    HEALING_TIME_BASE = 60

    def __init__(self):
        self.airports = {}
        self.interconnections = []
        self.departure_risks = []
        self.diversion_risks = []

    def _get_db_connection(self):
        try:
            connection = mysql.connector.connect(**self.DB_CONFIG)
            return connection
        except mysql.connector.Error as errors:
            raise mysql.connector.Error(f"Database connection failed: {errors}")

    def _load_emergency_data(self):
        self.airports.clear()
        self.interconnections.clear()
        self.departure_risks.clear()

        self.airports.update({
            'OTHH': {'Name': 'Hamad International Airport', 'Continent': 'Asia', 'Country': 'Qatar',
                     'Latitude': 25.273500, 'Longitude': 51.608300,
                     'Clinic': True, 'Healing': 25.0, 'TimeFactor': 0.75},
            'EGLL': {'Name': 'London Heathrow Airport', 'Continent': 'Europe', 'Country': 'United Kingdom',
                     'Latitude': 51.470000, 'Longitude': -0.454300,
                     'Clinic': True, 'Healing': 20.0, 'TimeFactor': 0.50},
            'KJFK': {'Name': 'John F. Kennedy Airport', 'Continent': 'North America',
                     'Country': 'United States',
                     'Latitude': 40.641300, 'Longitude': -73.778100,
                     'Clinic': False},
            'WSSS': {'Name': 'Singapore Changi Airport', 'Continent': 'Asia', 'Country': 'Singapore',
                     'Latitude': 1.364400, 'Longitude': 103.991500,
                     'Clinic': True, 'Healing': 15.0, 'TimeFactor': 0.80},
            'PADD': {'Name': 'Addu International Airport', 'Continent': 'Asia', 'Country': 'Maldives',
                     'Latitude': 0.697400, 'Longitude': 73.158100,
                     'Clinic': False},
        })
        self.interconnections.extend([
            {'Departure_Airport_ID': 'OTHH', 'Arrival_Airport_ID': 'EGLL', 'Time': 420,
             'Health_Cost_Per_Minute': 0.045},
            {'Departure_Airport_ID': 'OTHH', 'Arrival_Airport_ID': 'WSSS', 'Time': 460,
             'Health_Cost_Per_Minute': 0.040},
            {'Departure_Airport_ID': 'EGLL', 'Arrival_Airport_ID': 'KJFK', 'Time': 450,
             'Health_Cost_Per_Minute': 0.055},
            {'Departure_Airport_ID': 'WSSS', 'Arrival_Airport_ID': 'EGLL', 'Time': 700,
             'Health_Cost_Per_Minute': 0.050},
            {'Departure_Airport_ID': 'OTHH', 'Arrival_Airport_ID': 'PADD', 'Time': 240,
             'Health_Cost_Per_Minute': 0.035},
            {'Departure_Airport_ID': 'PADD', 'Arrival_Airport_ID': 'OTHH', 'Time': 240,
             'Health_Cost_Per_Minute': 0.035},
        ])
        self.departure_risks.extend([
            {'Name': 'Weather Delay', 'Probability': 0.50, 'TimePenalty': 60, 'HealthPenalty': 4.80},
        ])

        if not self.airports or not self.interconnections:
            sys.exit()

    def load_from_database(self):
        connection = None
        cursor = None
        try:
            connection = self._get_db_connection()
            cursor = connection.cursor(dictionary=True)

            airport_sql_query = """
                                SELECT A.ICAO_Code, \
                                       A.Airport_Name, \
                                       C.Continent_Name, \
                                       A.Country_Name,
                                       A.Latitude, \
                                       A.Longitude, \
                                       A.Clinic, \
                                       A.Clinic_Healing_Amount, \
                                       A.Clinic_Time_Factor
                                FROM Airport AS A \
                                         INNER JOIN Continent AS C ON A.Continent_ID = C.Continent_ID \
                                """
            cursor.execute(airport_sql_query)
            for row in cursor.fetchall():
                icao_code = row['ICAO_Code']
                is_clinic = bool(row.get('Clinic', 0))
                airport_data = {
                    'Name': row['Airport_Name'], 'Continent': row.get('Continent_Name', 'Unknown'),
                    'Country': row.get('Country_Name', 'Unknown'),
                    'Latitude': float(row.get('Latitude', 0.0)),
                    'Longitude': float(row.get('Longitude', 0.0)),
                    'Clinic': is_clinic,
                }
                if is_clinic:
                    airport_data.update({'Healing': float(row.get('Clinic_Healing_Amount', 0.0)),
                                         'TimeFactor': float(row.get('Clinic_Time_Factor', 1.0))})
                self.airports[icao_code] = airport_data

            interconnection_sql_query = """
                                        SELECT Departure_Airport_ID, \
                                               Arrival_Airport_ID, \
                                               Travel_Time_Minutes, \
                                               Health_Cost_Per_Minute
                                        FROM Interconnection \
                                        """
            cursor.execute(interconnection_sql_query)
            for row in cursor.fetchall():
                self.interconnections.append({
                    'Departure_Airport_ID': row['Departure_Airport_ID'],
                    'Arrival_Airport_ID': row['Arrival_Airport_ID'],
                    'Time': int(row['Travel_Time_Minutes']),
                    'Health_Cost_Per_Minute': float(row['Health_Cost_Per_Minute']),
                })

            sql_query_departure_risk = "SELECT Departure_Risk_Name, Probability_of_Occurring, Time_Delay_Minutes, Health_Loss FROM Departure_Risk"
            cursor.execute(sql_query_departure_risk)
            for row in cursor.fetchall():
                self.departure_risks.append({
                    'Name': row['Departure_Risk_Name'], 'Probability': float(row['Probability_of_Occurring']),
                    'TimePenalty': int(row['Time_Delay_Minutes']), 'HealthPenalty': float(row['Health_Loss']),
                })

            if not self.airports or not self.interconnections:
                self._load_emergency_data()

        except mysql.connector.Error:
            self._load_emergency_data()

        finally:
            if cursor: cursor.close()
            if connection and connection.is_connected(): connection.close()


class GameState:

    def __init__(self, data_manager: GameData):
        self.data = data_manager
        self.current_health = data_manager.START_HEALTH
        self.total_time_minutes = 0
        self.current_location_icao = None
        self.target_hospital_icao = None
        self.messages = []
        self.is_game_over = False
        self.outcome = None

    def initialize(self):
        all_icaos = list(self.data.airports.keys())

        if not all_icaos:
            raise Exception("No airport data available. Cannot start game.")

        possible_starts = [icao for icao in all_icaos if
                           any(conn['Departure_Airport_ID'] == icao for conn in self.data.interconnections)]

        if not possible_starts:
            raise Exception("No valid starting locations available from loaded data.")

        self.current_location_icao = random.choice(possible_starts)

        icao_remaining = [icao for icao in all_icaos if icao != self.current_location_icao]
        if not icao_remaining:
            raise Exception("Only one airport loaded. Cannot set a destination.")

        self.target_hospital_icao = random.choice(icao_remaining)

        self.messages.append(
            f"GOAL: Deliver patient to {self.data.airports[self.target_hospital_icao]['Name']} ({self.target_hospital_icao})."
        )

        return {
            'current_health': self.current_health, 'total_time_minutes': self.total_time_minutes,
            'current_location_icao': self.current_location_icao, 'target_hospital_icao': self.target_hospital_icao,
            'messages': self.messages, 'is_game_over': self.is_game_over, 'outcome': self.outcome
        }

    def load_from_session(self, session_data):
        self.current_health = session_data['current_health']
        self.total_time_minutes = session_data['total_time_minutes']
        self.current_location_icao = session_data['current_location_icao']
        self.target_hospital_icao = session_data['target_hospital_icao']
        self.messages = session_data.get('messages', [])
        self.is_game_over = session_data.get('is_game_over', False)
        self.outcome = session_data.get('outcome')

    def check_game_over(self):
        if self.current_health <= 0:
            self.outcome = "LOST_HEALTH"
            self.is_game_over = True
            self.messages.append(
                "😭 MISSION OVER, Despite your efforts We lost the patient. (Health dropped to 0).")
        elif self.total_time_minutes >= self.data.MAXIMUM_TIME_MINUTES:
            self.outcome = "LOST_TIME"
            self.is_game_over = True
            self.messages.append(
                "😭 MISSION OVER: Time limit exceeded. Ending Session..")
        elif self.current_location_icao == self.target_hospital_icao and self.current_health > 0:
            self.outcome = "SUCCESS"
            self.is_game_over = True
            self.messages.append(
                "🏆 MISSION SUCCESS & LIFE SAVED: Patient now is in experts hand!")

        return self.is_game_over

    def check_risk(self, risk_list):
        if not risk_list: return None
        for risk in risk_list:
            if random.random() < risk['Probability']: return risk
        return None

    def get_flight_info(self, departure_icao, arrival_icao):
        return next((conn for conn in self.data.interconnections if
                     conn['Departure_Airport_ID'] == departure_icao and conn['Arrival_Airport_ID'] == arrival_icao),
                    None)

    def execute_healing(self):
        healing_data = self.data.airports[self.current_location_icao]
        time_cost = self.data.HEALING_TIME_BASE * healing_data.get('TimeFactor', 1.0)
        health_gain = healing_data.get('Healing', 0.0)

        self.total_time_minutes += int(round(time_cost))
        self.current_health = min(self.data.START_HEALTH, self.current_health + health_gain)

        self.messages.append(
            f"--- HEALING COMPLETE: Health +{health_gain:.2f} HP. Time Taken: {int(round(time_cost))} min. ---")

        return self.check_game_over()

    def execute_flight(self, flight_information):
        time_cost = flight_information['Time']
        health_cost = flight_information['Health_Loss']

        self.current_health -= health_cost
        self.total_time_minutes += time_cost

        if self.check_game_over(): return True

        self.current_location_icao = flight_information['Destination_ICAO']
        destination_airport = self.data.airports[self.current_location_icao]

        self.messages.append(
            f"--- FLIGHT ARRIVAL: Arrived at {destination_airport['Name']} ({self.current_location_icao}). Health: -{health_cost:.2f} HP. ---")

        return self.check_game_over()

    def to_dict(self):
        return {
            'current_health': self.current_health, 'total_time_minutes': self.total_time_minutes,
            'current_location_icao': self.current_location_icao, 'target_hospital_icao': self.target_hospital_icao,
            'messages': self.messages, 'is_game_over': self.is_game_over, 'outcome': self.outcome
        }


class FlightToHealApp:

    def __init__(self):
        self.data_manager = GameData()
        self.data_manager.load_from_database()

        self.app = Flask(__name__)
        self.app.secret_key = 'your_super_secret_key_here'
        self.app.permanent_session_lifetime = timedelta(minutes=60)

        self._register_routes()

    def _register_routes(self):
        self.app.route('/')(self.index)
        self.app.route('/api/get_airport_coords', methods=['GET'])(self.get_airport_coords)
        self.app.route('/api/start_game', methods=['POST'])(self.start_game)
        self.app.route('/api/risk_check', methods=['POST'])(self.check_for_risk)
        self.app.route('/api/take_action', methods=['POST'])(self.take_action)

    def _get_current_state(self):
        if 'game_state' not in session:
            return None
        state = GameState(self.data_manager)
        state.load_from_session(session['game_state'])
        return state

    def _get_current_status_json(self, state: GameState):
        minutes_remaining = self.data_manager.MAXIMUM_TIME_MINUTES - state.total_time_minutes
        current_location_data = self.data_manager.airports[state.current_location_icao]
        target_location_data = self.data_manager.airports[state.target_hospital_icao]

        available_flights = []
        flight_id = 1
        for connection in self.data_manager.interconnections:
            if connection['Departure_Airport_ID'] == state.current_location_icao:
                health_cost = connection['Time'] * connection['Health_Cost_Per_Minute']
                available_flights.append({
                    'ID': flight_id, 'Destination_ICAO': connection['Arrival_Airport_ID'],
                    'Destination_Name': self.data_manager.airports[connection['Arrival_Airport_ID']]['Name'],
                    'Time': connection['Time'], 'Health_Loss': round(health_cost, 2),
                })
                flight_id += 1

        messages_to_send = state.messages.copy()
        state.messages = []

        return jsonify({
            'status': {
                'health': round(state.current_health, 2), 'time_total': state.total_time_minutes,
                'time_remaining': minutes_remaining, 'current_icao': state.current_location_icao,
                'current_name': current_location_data['Name'], 'target_icao': state.target_hospital_icao,
                'target_name': target_location_data['Name'], 'is_clinic': current_location_data.get('Clinic', False)
            },
            'options': available_flights, 'messages': messages_to_send,
            'game_over': state.is_game_over, 'outcome': state.outcome
        })

    def _update_game_status_in_db(self, state: GameState):
        if 'game_id' not in session:
            return

        game_status_text = 'Active'
        if state.is_game_over:
            game_status_text = 'Won' if state.outcome == 'SUCCESS' else 'Lost'

        conn = None
        try:
            conn = self.data_manager._get_db_connection()
            cursor = conn.cursor()

            sql = """
                  UPDATE game_state
                  SET Current_Patient_Health  = %s,
                      Total_Game_Time_Minutes = %s,
                      Current_Location_ID     = %s,
                      Game_Status             = %s
                  WHERE Game_ID = %s \
                  """

            cursor.execute(sql, (
                round(state.current_health, 2),
                state.total_time_minutes,
                state.current_location_icao,
                game_status_text,
                session['game_id']
            ))
            conn.commit()
        except mysql.connector.Error:
            pass
        finally:
            if conn:
                conn.close()

    def index(self):
        return render_template('index.html')

    def get_airport_coords(self):
        coords_map = {}
        for icao, data in self.data_manager.airports.items():
            coords_map[icao] = [data['Latitude'], data['Longitude']]
        return jsonify(coords_map)

    def start_game(self):
        try:
            data = request.get_json()
            player_name = data.get('player_name', 'Unknown Player')
            player_age = int(data.get('player_age', 0))

            initial_state_object = GameState(self.data_manager)
            initial_state_dict = initial_state_object.initialize()

            conn = self.data_manager._get_db_connection()
            cursor = conn.cursor()

            sql = """
                  INSERT INTO game_state
                  (Current_Patient_Health, Total_Game_Time_Minutes, Max_Allowed_Time_Minutes,
                   Current_Location_ID, Target_Hospital_ID, Game_Status, Player_Name, Player_Age)
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s) \
                  """

            cursor.execute(sql, (
                initial_state_dict['current_health'],
                initial_state_dict['total_time_minutes'],
                self.data_manager.MAXIMUM_TIME_MINUTES,
                initial_state_dict['current_location_icao'],
                initial_state_dict['target_hospital_icao'],
                'Active',
                player_name,
                player_age
            ))

            game_id = cursor.lastrowid
            conn.commit()
            cursor.close()
            conn.close()

            session.permanent = True
            session['game_state'] = initial_state_dict
            session['game_id'] = game_id
            session.pop('pending_flight', None)

            current_state = self._get_current_state()
            return self._get_current_status_json(current_state)

        except mysql.connector.Error as db_error:
            return jsonify(
                {'error': 'Database error: Failed to insert game status.', 'internal_error': str(db_error)}), 500
        except Exception as e:
            return jsonify({'error': str(e), 'internal_error': 'Initialization Failed'}), 500

    def check_for_risk(self):
        state = self._get_current_state()
        if not state:
            return jsonify({'error': 'Game not started.'}), 400

        data = request.get_json()
        target_icao = data.get('target_icao')

        chosen_flight = state.get_flight_info(state.current_location_icao, target_icao)

        if not chosen_flight:
            return jsonify({'error': 'Invalid flight option.'}), 400

        departure_risk = state.check_risk(self.data_manager.departure_risks)

        if departure_risk:
            state.total_time_minutes += departure_risk['TimePenalty']
            state.current_health -= departure_risk['HealthPenalty']

            is_over = state.check_game_over()

            if 'game_id' in session:
                self._update_game_status_in_db(state)

            session['game_state'] = state.to_dict()
            session['pending_flight'] = {
                'target_icao': target_icao,
                'time': chosen_flight['Time'],
                'health_cost_per_minute': chosen_flight['Health_Cost_Per_Minute']
            }

            return jsonify({
                'risk_found': True,
                'risk_details': {
                    'name': departure_risk['Name'],
                    'time_penalty': departure_risk['TimePenalty'],
                    'health_penalty': round(departure_risk['HealthPenalty'], 2)
                },
                'game_over_after_risk': is_over,
                'current_status': self._get_current_status_json(state).json
            })
        else:
            return jsonify({
                'risk_found': False,
                'target_icao': target_icao
            })

    def take_action(self):
        state = self._get_current_state()
        if not state:
            return jsonify({'error': 'Game not started. Please call /api/start_game'}), 400

        if state.is_game_over:
            return self._get_current_status_json(state)

        data = request.get_json()
        action_type = data.get('action')

        state.messages = []
        state_changed = False

        if action_type == 'heal':
            if not self.data_manager.airports[state.current_location_icao].get('Clinic', False):
                state.messages.append("🚫 No clinic here. Cannot heal.")
            else:
                state.execute_healing()
                state_changed = True

        elif action_type == 'fly_execute':
            target_icao = session.pop('pending_flight', {}).get('target_icao') or data.get('target_icao')

            if not target_icao:
                state.messages.append("🚫 Error: Flight target missing for execution.")
            else:
                chosen_flight = state.get_flight_info(state.current_location_icao, target_icao)

                if not chosen_flight:
                    state.messages.append("🚫 Error: Invalid flight option during execution.")
                else:
                    health_cost = chosen_flight['Time'] * chosen_flight['Health_Cost_Per_Minute']
                    flight_info = {
                        'Destination_ICAO': target_icao, 'Time': chosen_flight['Time'], 'Health_Loss': health_cost,
                    }
                    state.execute_flight(flight_info)
                    state_changed = True

        elif action_type == 'fly_cancel':
            state.messages.append("🛫 Flight cancelled due to departure risk. Patient stabilized locally.")
            session.pop('pending_flight', None)
            state_changed = True

        else:
            state.messages.append("🚫 Invalid action.")

        session['game_state'] = state.to_dict()

        if state_changed or state.is_game_over:
            self._update_game_status_in_db(state)

        return self._get_current_status_json(state)

    def run(self, debug=True):
        self.app.run(debug=debug)


if __name__ == '__main__':
    app_instance = FlightToHealApp()
    app_instance.run(debug=True)