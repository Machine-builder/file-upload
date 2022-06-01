from connections import ebsocket_event
from socket_conn import ebsocket_server
from socket_conn import ebsocket_system
from socket_conn import utility as ebsocket_utility

server_address = (
    ebsocket_utility.get_local_ip(),
    9882
)
server = ebsocket_server(server_address)
system = ebsocket_system(server)

print("Server address:", server_address)

while True:

    new_clients, new_events, disonnected_clients = system.pump()

    for client in new_clients:
        print("New client:", client)
        conn, addr = client
    
    for event in new_events:
        if event.event == 'test_event':
            print("Event is test_event")
        
        elif event.event == 'OBJ_TRANSLATE_CLIENT':
            # one client moves an object,
            # send info to other client
            from_conn = event.from_connection
            send_event = ebsocket_event(
                "OBJECT_TRANSLATE",
                object_tag=event.obj_name,
                location=event.location)
            for conn in system.clients:
                if conn == from_conn:
                    # don't send this event
                    # to the client that
                    # originally sent this
                    # event
                    continue
                system.send_event_to(conn, send_event)
            
        else:
            print("Unhandled event received:", event)

    
    for client in disonnected_clients:
        print("Client disconnected:", client)