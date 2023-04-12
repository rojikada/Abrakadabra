# -*- coding: utf-8 -*-
import json

import requests
import dash
from dash import dcc
from dash import html, dash_table
from dash.dependencies import Input, Output
from furl import furl
from urllib.parse import quote
import pandas as pd

app = dash.Dash(__name__)

app.config.suppress_callback_exceptions = True
app.layout = html.Div([
    # represents the URL bar, doesn't render anything
    dcc.Location(id='url', refresh=False),

    # content will be rendered in this element
    html.Div(id='content'),
])


class AbraAPI:
    url = ""
    authSessionId = ""

    def __init__(self, url, authSessionId):
        self.url = url
        self.authSessionId = authSessionId
        self.settingsKey = "key:moje-aplikace:pravidla"
        self.settings = {
            "assignment_rules": [{"ruleSetId": 0, "sumCelkemEq": 10, "nazFirmyEq": "Microsoft"}],
            "sets": [{
                "name": "Test",
                "rules": [
                    {"type": "percent", "name": "Procenta", "value": 20.},
                    {"type": "fixed", "name": "Fixní částka", "value": 2000.},
                    {"type": "rest", "name": "Zbytek"},
                ]
            }]
        }  # {}


    def data_wrapper(self, data):
        structure = {
            "winstrom": data
        }
        structure["winstrom"]["@version"] = "1.0"
        return structure

    def get_faktura(self, faktura_id):
        response = requests.get(
            f'{self.url}/faktura-prijata/{faktura_id}.json?detail=full&authSessionId={self.authSessionId}')
        if response.status_code == 200:
            data = response.json()["winstrom"]["faktura-prijata"][0]
            return data
        else:
            raise ConnectionError("AbraAPI: Unable to load data")

    def get_settings(self):
        response = requests.get(f'{self.url}/global-store/(id="{quote(self.settingsKey)}").json',
                                headers={"X-AuthSessionId": self.authSessionId})
        if response.status_code == 200:
            self.settings = json.loads(response.json()["winstrom"]["global-store"][0]["hodnota"])
        else:
            raise ConnectionError("AbraAPI: Unable to load settings")

    def find_set(self, name):
        for setId in range(len(self.settings["sets"])):
            set = self.settings["sets"][setId]
            if set["name"] == name:
                return set, setId

    def calculate_costs(self, set_name, sum_costs):
        sum_costs = float(sum_costs)
        set, setId = self.find_set(set_name)
        current_cost = 0
        items = []
        for rule in set["rules"]:
            if rule["type"] == "fixed":
                value = rule["value"]
                current_cost += value
            elif rule["type"] == "percent":
                print(rule, sum_costs)
                value = sum_costs * rule["value"] / 100.
                current_cost += value
            elif rule["type"] == "rest":
                value = max(0, sum_costs - current_cost)
                current_cost += value

            items.append({"name": rule["name"], "type": rule["type"]})
            if "value" in rule:
                items[-1]["value"] = rule["value"]
            items[-1]["costs"] = value
            if current_cost > sum_costs:
                return False, []
        if current_cost != sum_costs:
            return False, []
        return True, items

    def get_settings_dropdown(self):
        sets = []
        for setId in range(len(self.settings["sets"])):
            set = self.settings["sets"][setId]
            sets.append(set["name"])
        dropdown = dcc.Dropdown(sets, id="rule-set")
        return dropdown

    def set_settings(self):
        response = requests.post(f'{self.url}/global-store.json', json=self.data_wrapper(
            {"global-store": [{"id": self.settingsKey, "hodnota": json.dumps(self.settings)}]}),
                                 headers={"Content-Type": "application/json", "X-AuthSessionId": self.authSessionId})
        return response

    def get_(self):
        pass


@app.callback(
    Output('set-name', 'value'),
    [Input('rule-set', 'value')]
)
def update_output(value):
    return value


@app.callback(Output('content', 'children'),
              [Input('url', 'href')])
def _content(href: str):
    f = furl(href)
    url = f.args["companyUrl"]
    authSessionId = f.args["authSessionId"]
    api = AbraAPI(url, authSessionId)
    faktura = None
    links = []

    if "objectIds" in f.args:
        for fakturaId in f.args["objectIds"].split(","):
            link = furl(href)
            link.args["objectId"] = fakturaId
            del link.args["objectIds"]
            if faktura is None:
                faktura = api.get_faktura(fakturaId)
            else:
                links.append(link)
    if "objectId" in f.args:
        faktura = api.get_faktura(f.args["objectId"])

    isOk, items = api.calculate_costs("Test", faktura["sumCelkem"])
    if isOk:
        rows = []
        for item in items:
            value = ""
            if "value" in item:
                value = dcc.Input(value=item["value"], type="number")

            rows.append(html.Div([html.Div(dcc.Input(value=item["name"], type="text")),
                             html.Div(dcc.Dropdown([
                                 {"value": "percent", "label": "Procenta"},
                                 {"value": "fixed", "label": "Fixní"},
                                 {"value": "rest", "label": "Zbytek"}
                             ],
                                 item["type"]
                             )),
                             html.Div(value),
                             html.Div(str(item["costs"])+" Kč"),
                             ]))
        table = html.Div(rows, style={"display":"flex"})

    return html.Div([
        html.H2(children="Firma: "+faktura["nazFirmy"]),
        html.P(children="Popis: "+faktura["popis"]),
        api.get_settings_dropdown(),
        dcc.Input(id='set-name', type='text', placeholder='Název setu'),
        table,
        html.Button('Uložit', id='save', n_clicks=0)
    ])


if __name__ == '__main__':
    app.run_server(debug=True, port=3000)
