"""The Restocker Component for this Cloud Computing project.

This component checks the store's stock to ensure that a pizza-order request can be filled. 
If stock is insufficient, then this component performs a restock for the insufficient items. 
As a secondary function, this component scans the database at the end of every day to check 
for items that might need to be restocked.
"""

import json
import logging
import os
import threading
import time
import uuid

import jsonschema
import requests
from cassandra.cluster import Cluster
from quart import Quart, Response, request
from quart.utils import run_sync

__author__ = "Carla Vazquez, Chris Scott"
__version__ = "2.0.0"
__maintainer__ = "Chris Scott"
__email__ = "cms190009@utdallas.edu"
__status__ = "Development"

# Connect to casandra service
cass_IP = os.environ["CASS_DB"]
cluster = Cluster([cass_IP])
session = cluster.connect('pizza_grocery')

# prepared statements
while True:
    try:
        get_quantity = session.prepare('\
            SELECT quantity \
            FROM stock  \
            WHERE storeID = ? AND itemName = ?\
        ')
        add_stock_prepared = session.prepare('\
            UPDATE stock \
            SET quantity = ?  \
            WHERE storeID = ? AND itemName = ?\
        ')
        get_stores = session.prepare("SELECT storeID FROM stores")
        get_items = session.prepare("SELECT name FROM items")
        select_stock_prepared = session.prepare('SELECT * FROM stock WHERE storeID=?')
        update_stock_prepared = session.prepare('\
            UPDATE stock \
            SET quantity=? \
            WHERE storeID=? AND itemName=?\
        ')
    except:
        time.sleep(5)
    else:
        break

# set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# create Quart app
app = Quart(__name__)

# Open jsonschema for workflow-request
with open("src/workflow-request.schema.json", "r") as workflow_schema:
    workflow_schema = json.loads(workflow_schema.read())

# Global pizza items/ingredients dict
items_dict = {
    'Dough': 0,         'SpicySauce': 0,        'TraditionalSauce': 0,  'Cheese': 0,
    'Pepperoni': 0,     'Sausage': 0,           'Beef': 0,              'Onion': 0,
    'Chicken': 0,       'Peppers': 0,           'Olives': 0,            'Bacon': 0,
    'Pineapple': 0,     'Mushrooms': 0
}

# Global workflows dict
workflows = dict()


async def get_next_component(store_id):
    comp_list = workflows[store_id]["component-list"].copy()
    comp_list.remove("cass")
    next_comp_index = comp_list.index("restocker") + 1
    if next_comp_index >= len(comp_list):
        return None
    return comp_list[next_comp_index]


async def get_component_url(component, store_id):
    workflow_offset = str(workflows[store_id]["workflow-offset"])
    comp_name = component +\
        (workflow_offset if workflows[store_id]["method"] == "edge" else "")
    url = "http://" + comp_name + ":"
    if component == "order-verifier":
        url += "1000/order"
    elif component == "delivery-assigner":
        url += "3000/order"
    elif component == "stock-analyzer":
        url += "4000/order"
    elif component == "order-processor":
        url += "6000/order"
    return url


async def send_order_to_next_component(url, order):
    # send order to next component
    def request_post():
        return requests.post(url, json=json.dumps(order))
    
    r = await run_sync(request_post)()
    
    # form log message based on response status code from next component
    message = "Order from " + order["pizza-order"]["custName"] + " is valid."
    if r.status_code == 200:
        logging.info(message + " Order sent to next component.")
        return Response(status=200, response=json.dumps(json.loads(r.text)))
    else:
        logging.info(message + " Issue sending order to next component:\n" + r.text)
        return Response(status=r.status_code, response=r.text)


async def send_results_to_client(store_id, order):
    # form results message for Restaurant Owner (client)
    cust_name = order["pizza-order"]["custName"]
    message = "Order for " + cust_name
    if "assignment" in order:
        delivery_entity = order["assignment"]["deliveredBy"]
        estimated_time = str(order["assignment"]["estimatedTime"])
        message += " will be delivered in " + estimated_time
        message += " minutes by delivery entity " + delivery_entity + "."
    else:
        message += " has been placed."
    
    # send results message json to Restaurant Owner
    origin_url = "http://" + workflows[store_id]["origin"] + ":8080/results"
    
    def request_post():
        return requests.post(origin_url, json=json.dumps({"message": message}))

    r = await run_sync(request_post)()

    # form log message based on response status code from Restaurant Owner
    message = "Sufficient stock for order from " + cust_name + "."
    if r.status_code == 200:
        logging.info(message + " Restuarant Owner received the results.")
        return Response(status=r.status_code, response=json.dumps(order))
    else:
        logging.info(message + " Issue sending results to Restaurant Owner:\n" + r.text)
        return Response(status=r.status_code, response=r.text)


# Decrement a store's stock for the order about to be placed
async def decrement_stock(store_uuid, instock_dict, required_dict):
    for item_name in required_dict:
        quantity = instock_dict[item_name] - required_dict[item_name]
        session.execute(update_stock_prepared, (quantity, store_uuid, item_name))


# Aggregate all ingredients for a given order
async def aggregate_ingredients(pizza_list):
    ingredients = items_dict.copy()

    # Loop through each pizza in pizza_list and aggregate the required ingredients
    for pizza in pizza_list:
        if pizza['crustType'] == 'Thin':
            ingredients['Dough'] += 1
        elif pizza['crustType'] == 'Traditional':
            ingredients['Dough'] += 2

        if pizza['sauceType'] == 'Spicy':
            ingredients['SpicySauce'] += 1
        elif pizza['sauceType'] == 'Traditional':
            ingredients['TraditionalSauce'] += 1

        if pizza['cheeseAmt'] == 'Light':
            ingredients['Cheese'] += 1
        elif pizza['cheeseAmt'] == 'Normal':
            ingredients['Cheese'] += 2
        elif pizza['cheeseAmt'] == 'Extra':
            ingredients['Cheese'] += 3

        for topping in pizza["toppingList"]:
            ingredients[topping] += 1

    return ingredients


# Check stock at a given store to determine if order can be filled
async def check_stock(store_uuid, order_dict):
    instock_dict = items_dict.copy()
    required_dict = await aggregate_ingredients(order_dict["pizzaList"])
    restock_list = list()   # restock_list will be empty if no items need restocking

    rows = session.execute(select_stock_prepared, (store_uuid,))
    for row in rows:
        if row.quantity < required_dict[row.itemname]:
            quantity_difference = \
                required_dict[row.itemname] - instock_dict[row.itemname]
            restock_list.append(
                {"item-name": row.itemname, "quantity": quantity_difference}
            )
        instock_dict[row.itemname] = row.quantity

    return instock_dict, required_dict, restock_list


# the order endpoint
@app.route('/order', methods=['POST'])
async def restocker():
    logging.info("POST /order")
    request_data = await request.get_json()
    order = json.loads(request_data)

    if order["pizza-order"]["storeId"] not in workflows:
        message = "Workflow does not exist. Request Rejected."
        logging.info(message)
        return Response(status=422, response=message)

    store_id = order["pizza-order"]["storeId"]
    store_uuid = uuid.UUID(store_id)

    valid = True
    mess = None
    try:
        # check stock
        instock_dict, required_dict, restock_list = \
            await check_stock(store_uuid, order["pizza-order"])
        # restock, if needed
        if restock_list:
            # perform restock
            for item_dict in restock_list:
                new_quantity = \
                    item_dict["quantity"] + instock_dict[item_dict["item-name"]] + 10
                instock_dict[item_dict["item-name"]] = new_quantity
                session.execute(
                    add_stock_prepared, 
                    (new_quantity, store_uuid, item_dict["item-name"])
                )
        # decrement stock
        await decrement_stock(store_uuid, instock_dict, required_dict)
    except Exception as inst:
        valid = False
        mess = inst.args[0]

    if valid:
        next_comp = await get_next_component(store_id)
        if next_comp is None:
            # last component in the workflow, report results to client
            resp = await send_results_to_client(store_id, order)
            return resp
        else:
            # send order to next component in workflow
            next_comp_url = await get_component_url(next_comp, store_id)
            resp = await send_order_to_next_component(next_comp_url, order)
            return resp
    else:
        logging.info("Request rejected, restock failed:\n" + mess)
        return Response(
            status=400, 
            response="Request rejected, restock failed:\n" + mess
        )


async def verify_workflow(data):
    global workflow_schema
    valid = True
    mess = None
    try:
        jsonschema.validate(instance=data, schema=workflow_schema)
    except Exception as inst:
        valid = False
        mess = inst.args[0]
    return valid, mess


###############################################################################
#                           API Endpoints
###############################################################################

# if workflow-request is valid and does not exist, create it
@app.route("/workflow-requests/<storeId>", methods=['PUT'])
async def setup_workflow(storeId):
    logging.info("PUT /workflow-requests/" + storeId)
    request_data = await request.get_json()
    data = json.loads(request_data)
    # verify the workflow-request is valid
    valid, mess = await verify_workflow(data)

    if not valid:
        logging.info("workflow-request ill formatted")
        return Response(
            status=400, 
            response="workflow-request ill formatted\n" + mess
        )

    if storeId in workflows:
        logging.info("Workflow " + storeId + " already exists")
        return Response(
            status=409, 
            response="Workflow " + storeId + " already exists\n"
        )

    workflows[storeId] = data

    logging.info("Workflow started for Store " + storeId)

    return Response(
        status=201, 
        response="Restocker deployed for {}\n".format(storeId)
    )    


# if the recource exists, update it
@app.route("/workflow-update/<storeId>", methods=['PUT'])
async def update_workflow(storeId):
    logging.info("PUT /workflow-update/" + storeId)
    request_data = await request.get_json()
    data = json.loads(request_data)
    # verify the workflow-request is valid
    valid, mess = await verify_workflow(data)

    if not valid:
        logging.info("workflow-request ill formatted")
        return Response(
            status=400, 
            response="workflow-request ill formatted\n" + mess
        )

    if not ("cass" in data["component-list"]):
        logging.info("Update rejected, cass is a required workflow component")
        return Response(
            status=422, 
            response="Update rejected, cass is a required workflow component.\n"
        )

    workflows[storeId] = data

    logging.info("Restocker updated for Store " + storeId)

    return Response(
        status=200, 
        response="Restocker updated for {}\n".format(storeId)
    )


# delete the specified resource, if it exists
@app.route("/workflow-requests/<storeId>", methods=["DELETE"])
async def teardown_workflow(storeId):
    if storeId not in workflows:
        return Response(
            status=404, 
            response="Workflow doesn't exist. Nothing to teardown.\n"
        )
    else:
        del workflows[storeId]
        logging.info("Restocker stopped for {}\n".format(storeId))
        return Response(status=204)


# retrieve the specified resource, if it exists
@app.route("/workflow-requests/<storeId>", methods=["GET"])
async def retrieve_workflow(storeId):
    logging.info("GET /workflow-requests/" + storeId)
    if not (storeId in workflows):
        return Response(
            status=404, 
            response="Workflow doesn't exist. Nothing to retrieve.\n"
        )
    else:
        return Response(
            status=200, 
            response=json.dumps(workflows[storeId])
        )


# retrieve all resources
@app.route("/workflow-requests", methods=["GET"])
async def retrieve_workflows():
    logging.info("GET /workflow-requests")
    return Response(status=200, response=json.dumps(workflows))


# the health endpoint, to verify that the server is up and running
@app.route('/health', methods=['GET'])
async def health_check():
    logging.info("GET /health")
    return Response(status=200, response="healthy\n")


# scan the database for items that are out of stock or close to it
async def scan_out_of_stock():
    # gets a list of active store workflows
    stores = workflows.keys()
    # loops through said stores
    for store_id in stores:
        store_uuid = uuid.UUID(store_id)
        # gets a list of all items
        items = session.execute(get_items)
        # loops through said items
        for item in items:
            # if the item exsists at the store
            quantity = session.execute(get_quantity, (store_uuid, item.name))
            quantity_row = quantity.one()
            if quantity_row != None:
                # and it is low in quantity
                if quantity_row.quantity < 10.0:
                    # restock it
                    new_quantity = 50
                    session.execute(add_stock_prepared, (new_quantity, store_uuid, item.name))
                    logging.info("Store " + store_id + " Daily Scan:\n\t" + \
                        item.name + " restocked to " + str(new_quantity)
                    )
    # if app.config["ENV"] == "production": 
    threading.Timer(60, scan_out_of_stock).start()

# call scan_out_of_stock() for the first time
scan_out_of_stock()
