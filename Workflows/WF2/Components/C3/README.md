# Delivery Assigner
Workflow 2, Component 3

## Written By
Randeep Singh Ahlawat

## Description
This component receives an order from the workflow manager and does analysis between the delivery entities, the store, and customer location to determine which entity to assign to the order to get the shortest delivery time.

## Setup
Machine requirements:
* Python 3.8
* Docker

Package requirements:
* pipenv

Packages installed on pipenv virtual environment:
* quart
* cassandra-driver
* requests

## Commands
* To build the image:
  ```
  docker build --rm -t trishaire/delivery-assigner:tag path_to_c3_dockerfile
  ```
* To update the repository:
  ```
  sudo docker login
  docker push trishaire/delivery-assigner:tag
  ```
* To create the service type the following command:
  ```
  docker service create --name delivery-assigner --network myNet --publish 3000:3000 --env CASS_DB=VIP_of_Cass_Service trishaire/delivery-assigner:tag
  ```
  * where `VIP_of_Cass_Service` is the VIP of `myNet` overlay network and `tag` is the tag of order-verifier image.

## Endpoints

### `POST /order`

#### Body

Requires a JSON object containing a [`pizza-order`](https://github.com/CPVazquez/CS6343Linear/blob/main/Workflows/WF2/Components/C1/src/pizza-order.schema.json) JSON object.

| field | type | required | description |
|-------|------|----------|-------------|
| pizza-order | `pizza-order` | true | the pizza order object |

`pizza-order` 

| field | type | required | description |
|-------|------|----------|-------------|
| orderId | string - format uuid | false | A base64 ID give to each order to identify it |
| storeId | string - format uuid | true | A base64 ID given to each store to identify it |
| custName | string | true | The name of the customer, as a single string for both first/last name |
| paymentToken | string - format uuid | true | The token for the third-party payment service that the customer is paying with |
| paymentTokenType | string | true | The type of token accepted (paypal, google pay, etc) |
| custLocation | `location` | true | The location of the customer, in degrees latitude and longitude |
| orderDate | string - date-time format | true | The date of order creation |
| pizzaList | `pizza` array | true | The list of pizzas that have been ordered |

`location`

| field | type | required | description |
|-------|------|----------|-------------|
| lat | number | false | Customer latitude in degrees |
| lon | number | false | Customer longitude in degrees |

`pizza`

| field | type | options | required | description |
|-------|------|---------|----|---|
| crustType | enum | Thin, Traditional | false | The type of crust |
| sauceType | enum | Spicy, Traditional | false | The type of sauce |
| cheeseAmt | enum | None, Light, Normal, Extra | false | The amount of cheese on the pizza |
| toppingList | enum array | Pepperoni, Sausage, Beef, Onion, Chicken, Peppers, Olives, Bacon, Pineapple, Mushrooms | false | The list of toppings added at extra cost (verified by server) |

#### Responses

| status code | status | meaning |
|-------------|--------|---------|
| 200 | Created | delivery entity successfully assigned. Estimated delivery time calculated |
| 208 | Error Already Reported | Indicates an error occurred in a subsequent component, just return the response |
| 404 | Not Found | delivery-assigner is not part of the given workflow and cannot process the request |

#### Forwarding

adds the following fields to the initally received JSON object before forwarding it on to the next component or returning it back to the data source.

| field | type | required | description |
|-------|------|----------|-------------|
| assignment | `assignment` | true | a JSON object containing assignment fields |

`assignment`

| field | type | required | description |
|-------|------|----------|-------------|
| deliveredBy | string | true | the name of the delivering entity |
| estimatedTime | number | true | the estimated time the delivery will take |

### `PUT /workflow-requests/<storeId>`

#### Parameters

| parameter | type | required | description |
|-------|------|----|---|
|storeId | string - format uuid | true | the id of the store issuing the workflow request|

#### Body

Requires a [`workflow-request`](https://github.com/CPVazquez/CS6343Linear/blob/main/Workflows/WF2/Components/C1/src/workflow-request.schema.json) JSON object. 

`workflow-request`
| field | type | options | required | description |
|-------|------|---------|----|---|
| method | enum | persistent, edge | true | the workflow deployment method |
| component-list| enum array| order-verifier, cass, delivery-assigner, stock-analyzer, restocker, order-processor | true | the components the workflow is requesting|
| origin | string - format ip | N/A| true | the ip of the host issuing the request|
| workflow-offset| integer | N/A| false | generated by the workflow manager and passed to other components|

#### Responses

| status code | status | meaning|
|---|---|---|
|201|Created| workflow successfully created|
|409|Conflict|a workflow already exists for the specified store, and thus a new one cannot be created|

### `PUT /workflow-update/<storeId>`

#### Parameters

| parameter | type | required | description |
|-----------|------|----------|-------------|
| storeId | string - format uuid | true | the id of the store issuing the workflow request |

#### Body

Requires a [`workflow-request`](https://github.com/CPVazquez/CS6343Linear/blob/main/Workflows/WF2/Components/C1/src/workflow-request.schema.json) JSON object. 

`workflow-request`

| field | type | options | required | description |
|-------|------|---------|----------|-------------|
| method | enum | persistent, edge | true | The workflow deployment method |
| component-list | enum array | order-verifier, cass, delivery-assigner, stock-analyzer, restocker, order-processor | true | The components the workflow is requesting |
| origin | string - format ip | N/A | true | The IP address of the host issuing the request |
| workflow-offset| integer | N/A | false | Generated by the workflow manager and passed to other components |

#### Responses

| status code | status | meaning|
|-------------|--------|--------|
| 200 | OK | The workflow was successfully updated |
| 422 | Unprocessable Entity | Request JSON is valid, but the `workflow-request` specifies an unsupported workflow |

### `DELETE /workflow-requests/<storeId>`

#### Parameters

| parameter | type | required | description |
|-------|------|----|---|
|storeId | string - format uuid| true| the id of the store whose workflow we want to delete|

#### Responses

| status code | status | meaning|
|---|---|---|
|204|No Content| the specified workflow was deleted successfully |
|404|Not Found| the specified workflow does not exist or has already been deleted

### `GET /workflow-requests/<storeId>`

#### Parameters

| parameter | type | required | description |
|-------|------|----|---|
|storeId | string - format uuid| true| the id of the store whose workflow we want to retrieve|

#### Responses

| status code | status | meaning|
|---|---|---|
|200| OK | returns the `workflow-request`|
|404| Not Found| the specified `workflow-request` does not exist and could not be retrieved|

### `GET /workflow-requests`

#### Responses

| status code | status | meaning|
|---|---|---|
|200| OK | returns all the `workflow-request`s on the delivery assinger component |


### `GET /health`

#### Responses
| status code | status | meaning|
|---|---|---|
|200| OK | The server is up and running  |

returns string `healthy` if the service is healthy

[Main README](https://github.com/CPVazquez/CS6343Linear)

