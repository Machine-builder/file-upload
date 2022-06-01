from os import stat
import socket
import pickle
import select
import errno
from typing import Union, List, Tuple
import logging


class utility:
    ...


class constants:
    ...


class ebsocket_base:
    ...


class ebsocket_event:
    ...


class utility():
    @staticmethod
    def any_type_join(l: list, j: str) -> str:
        '''concatenates a list of any object type with j as the connecting string'''
        return j.join([str(a) for a in l])

    @staticmethod
    def get_header(data: bytes, headersize: int = 16):
        '''generates a header for byte data'''
        return str(len(data)).rjust(headersize, '0').encode()

    @staticmethod
    def get_local_ip() -> str:
        '''gets local ipv4 address'''
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ipv4 = s.getsockname()[0]
        s.close()
        return ipv4


class constants:
    header_size = 16


class ebsocket_base(object):
    '''base class for both the server & client ebsocket classes'''

    def __init__(self, connection: socket.socket) -> None:
        self.connection = connection

    def is_valid_socket(self, socket_) -> socket.socket:
        '''if socket_ is a socket.socket instance the function returns it,
        otherwise returns the class instances' connection attribute'''
        if not isinstance(socket_, socket.socket):
            return self.connection
        return socket_

    def send_raw_to(self, data: bytes, connection: socket.socket):
        '''sends raw byte data to specific connection'''
        connection.send(data)

    def send_raw(self, data: bytes):
        '''sends raw byte data'''
        self.send_raw_to(data, self.connection)

    def recv_raw_from(self, buffersize: int = 34, connection: socket.socket = ...):
        '''receives a ray payload of the provided buffer size from a specific connection'''
        return connection.recv(buffersize)

    def recv_raw(self, buffersize: int = 512):
        '''receives a raw payload of the provided buffer size'''
        return self.recv_raw_from(buffersize, self.connection)

    def send_with_header(self, data: bytes, send_socket: socket.socket = None):
        '''sends data with a header'''
        use_socket = self.is_valid_socket(send_socket)
        byte_data = utility.get_header(data, constants.header_size)+data
        use_socket.send(byte_data)

    def recv_with_header(self, recv_socket: socket.socket = None):
        '''receives data with a header'''
        use_socket = self.is_valid_socket(recv_socket)
        header_recv = use_socket.recv(constants.header_size)
        total_bytes = int(header_recv.decode())
        data_recv = use_socket.recv(total_bytes)
        return data_recv

    def send_event(self, event: ebsocket_event = None, send_socket: socket.socket = None):
        '''sends an event using send_socket'''
        use_socket = self.is_valid_socket(send_socket)
        raw_bytes = event.as_bytes()
        return self.send_with_header(raw_bytes, use_socket)

    def recv_event(self, recv_socket: socket.socket = None):
        '''attempts to receive and return an event object, if the object
        received is not an event object, the function returns None'''
        use_socket = self.is_valid_socket(recv_socket)
        raw_bytes = self.recv_with_header(use_socket)
        event = ebsocket_event.from_bytes(raw_bytes)
        if isinstance(event, ebsocket_event):
            return event
        return None


class ebsocket_server(ebsocket_base):
    '''a server class used to handle multiple socket connections'''

    def __init__(self, bind_to: Union[tuple, int]):
        if isinstance(bind_to, int):
            bind_to = (utility.get_local_ip(), bind_to)
        self.address = bind_to
        self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connection.bind(self.address)

    def listen(self, backlog: int = 1):
        '''listens for incoming connections with a backlog'''
        self.connection.listen(backlog)

    def accept_connection(self) -> tuple:
        '''accepts next incoming connection and returns the connection and address'''
        connection, address = self.connection.accept()
        return connection, address


class ebsocket_client(ebsocket_base):
    '''a client class used to handle a single connection'''

    def __init__(self) -> None:
        self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        super().__init__(self.connection)

    def connect_to(self, address: tuple):
        '''try connect to an address, the connected attribute is
        a boolean which will be set to True if the connection is a success'''
        try:
            self.connection.connect(address)
            self.connected = True
            self.connection.setblocking(False)
        except:
            self.connected = False

    def pump(self):
        '''gets a list of all new events from the server

        also returns a boolean representing whether the connection
        is still active'''
        new_events = []

        try:
            while True:
                new_event = self.recv_event()
                if new_event is None:
                    return new_events, False
                new_events.append(new_event)

        except ConnectionResetError as e:
            logging.debug(f"connection reset error in get_new_events() -> {e}")
            return new_events, False

        except IOError as e:
            if e.errno != errno.EAGAIN and e.errno != errno.EWOULDBLOCK:
                # reading error
                logging.debug(f"reading error in get_new_events() -> {e}")

        except Exception as e:
            # general error
            logging.debug(f"general error in get_new_events() -> {e}")

        return new_events, True


class ebsocket_system(object):
    '''a whole server-client system network'''

    def __init__(self, server: ebsocket_server) -> None:
        self.server = server
        self.server.listen(5)
        self.connections_list = [self.server.connection]
        self.clients = {}
        self.timeout = 0.5

    def pump(self) -> Tuple[List[Tuple], List[ebsocket_event], List[Tuple]]:
        '''runs the main system

        run this function within a loop for basic functionality

        returns:
         - new_clients:list
         - new_events:list
         - disconnected_clients:list'''
        
        conn_list = self.connections_list
        read_connections, _, exception_connections = select.select(
            conn_list, [], conn_list, self.timeout)

        new_clients = []
        new_events = []
        disconnected_clients = []

        for notified_connection in read_connections:
            if notified_connection == self.server.connection:
                client_connection, client_address = self.server.accept_connection()
                self.connections_list.append(client_connection)
                self.clients[client_connection] = client_address
                new_clients.append((client_connection, client_address))

            else:
                try:
                    event = self.server.recv_event(notified_connection)
                except ConnectionResetError as e:
                    event = None
                    exception_connections.append(notified_connection)
                except ValueError as e:
                    event = None
                    exception_connections.append(notified_connection)

                if event is not None:
                    event.from_connection = notified_connection
                    new_events.append(event)

        for notified_connection in exception_connections:
            disconnected_clients.append(
                (notified_connection, self.clients[notified_connection]))
            self.remove_client(notified_connection)

        return new_clients, new_events, disconnected_clients

    def remove_client(self, client_connection):
        '''removes a client from the server'''
        self.connections_list.remove(client_connection)
        del self.clients[client_connection]

    def send_raw_to(self, connection: socket.socket, data: bytes):
        '''sends byte data to a client'''
        connection.send(data)

    def send_event_to(self, connection: socket.socket, event: ebsocket_event):
        '''sends an event to a client'''
        try:
            data = event.as_bytes()
            header = utility.get_header(data)
            self.send_raw_to(connection, header+data)
        except Exception as e:
            return False

    def send_event_to_clients(self, event: ebsocket_event):
        '''sends an event to all clients'''
        try:
            data = event.as_bytes()
            header = utility.get_header(data)
            full_bytes = header+data
            for connection in self.clients:
                self.send_raw_to(connection, full_bytes)
        except Exception as e:
            return False


class ebsocket_event(object):
    '''an event
    stores the event type and event data'''

    def __init__(self, event_data, **kwargs) -> None:
        self.from_connection = False
        if isinstance(event_data, str):
            self.__dict__ = {'event': event_data}
            self.__dict__.update(kwargs)
        elif isinstance(event_data, ebsocket_event):
            self.__dict__ = event_data.data
            self.from_connection = event_data.from_connection
        else:
            self.__dict__ = event_data
        self.event = self.__dict__.get('event', None)

    def get_attribute(self, attribute):
        '''gets an attribute of the event's data, if the attribute
        does not exist, returns None'''
        return self.__dict__.get(attribute, None)

    def compare_type(self, event_type:str) -> bool:
        '''compare the event's type with the provided argument'''
        return self.event == event_type

    def __repr__(self):
        return f'ebsocket_event<{self.event}>'
    
    def print_attributes(self):
        '''prints all event data attributes'''
        attribute_names = [k for k in self.__dict__]
        print(self)
        print('~ attributes ~')
        if len(attribute_names) > 0:
            longest = max([len(i) for i in attribute_names])
            for attribute_name in attribute_names:
                print(f' * {attribute_name.ljust(longest)}  :  {self.__dict__[attribute_name]}')
        else:
            print("event has no attributes")

    def as_bytes(self) -> bytes:
        '''compile the event into bytes'''
        json_data = {
            'event': self.event,
            '__dict__': self.__dict__}
        return pickle.dumps(json_data)
    
    @staticmethod
    def from_bytes(byte_data:bytes) -> ebsocket_event:
        '''decompile an event from bytes'''
        try:
            unpickled = pickle.loads(byte_data)
            event = ebsocket_event(
                unpickled.get('event',None),
                **unpickled.get('__dict__',{}))
            return event
        except:
            return None


if __name__ == '__main__':
    import time
    import bpy
    
    def getObjectByName(obj_name:str):
        return bpy.context.scene.objects.get(obj_name, None)
    
    # run a timer function to interact with server
    # stuff rather than one-off send/recv
    

    should_register = 1
    
    if should_register:
        client = ebsocket_client()
        ip = "192.168.15.22"
        port = 9882
        address = (ip, port)
        client.connect_to(address)
        
        socket_remote_objects = [
            # this object's motion is updated
            # from the server
            "Cube_Local_A",
            "Cube_Local_B"
        ]
        socket_local_objects = [
            # this object's motion is forwarded
            # to the server
            "Cube_Local_A",
            "Cube_Local_B"
        ]
        
        socket_local_objects_managed = []
        for obj_name in socket_local_objects:
            data = {
                'obj_name': obj_name,
                'obj': getObjectByName(obj_name),
                'last_loc': None
            }
            socket_local_objects_managed.append(data)
        
        socket_remote_objects_new = {}
        for obj_name in socket_remote_objects:
            socket_remote_objects_new[
                obj_name] = (obj_name, getObjectByName(obj_name))
        socket_remote_objects = socket_remote_objects_new


    def socketCheckTimerCalled():
        context = bpy.context
        scene = context.scene
        fps = scene.render.fps

        if not scene.property_socket_check_timer:
            print("stop timer within timer function, returning None")
            return None
        
        new_events, connected = client.pump()
        
        if not connected:
            print("Client lost connection, so timer stopped")
            return None
        
        updated_from_server = []
    
        for event in new_events:
        
            if event.event == 'OBJECT_TRANSLATE':
                new_location = event.location
                obj_info = socket_remote_objects.get(event.object_tag, None)
                obj_name, obj = obj_info
                if obj_info is None:
                    print("Provided object tag not present.")
                    print(event.object_tag)
                    continue
                if type(new_location) != tuple:
                    print("New location is not a tuple.")
                    continue
                if len(new_location) != 3:
                    print("New location len != 3.")
                    continue
                obj_name, obj = obj_info
                try:
                    obj.location.x = new_location[0]
                    obj.location.y = new_location[1]
                    obj.location.z = new_location[2]
                    print("Received object location update")
                    updated_from_server.append(obj_name)
                except:
                    # obj might've updated, may need refresh
                    socket_remote_objects[obj_name] = getObjectByName(obj_name)
                    print("Object required updating:", obj_name)
            
            else:
                print("Unhandled event received:", event)
        
        for data in socket_local_objects_managed:
            obj_name = data['obj_name']
            obj = data['obj']
            last_loc = data['last_loc']
            xyz = tuple(obj.location)
            if obj_name in updated_from_server:
                data['last_loc'] = xyz
                continue
            if last_loc != xyz:
                data['last_loc'] = xyz
                movement_event = ebsocket_event(
                    "OBJ_TRANSLATE_CLIENT",
                    obj_name = obj_name,
                    location = xyz)
                client.send_event(movement_event)
                print("Sent object location update")

        # run once every frame
        return (1/fps)
    
    properties = []
    new_property = (
        'property_test_v',
        bpy.props.IntProperty(name='', default=1),
        True)
    properties.append(new_property)
    new_property = (
        'property_socket_check_timer',
        bpy.props.BoolProperty(name='', default=True),
        False)
    properties.append(new_property)

    def register():
        # create custom properties
        for (prop_name, prop_value, _ur) in properties:
            setattr(bpy.types.Scene, prop_name, prop_value)

        context = bpy.context
        scene = context.scene

        scene.property_socket_check_timer = True
        bpy.app.timers.register(socketCheckTimerCalled)

    def unregister():
        for (prop_name, prop_value, _ur) in properties:
            if not _ur:
                continue
            try:
                delattr(bpy.types.Scene, prop_name)
            except AttributeError:
                print(f"WARNING: Property \"{prop_name}\" does not exist")

        context = bpy.context
        scene = context.scene
                
        scene.property_socket_check_timer = False
    
    if should_register:
        register()
    else:
        unregister()


    # print("Running client")

    # client = ebsocket_client()
    # ip = "192.168.15.22"
    # port = 9882
    # address = (ip, port)
    # client.connect_to(address)

    # event = ebsocket_event(
    #     'test_event',
    #     sample_tuple=(3, 6, 1),
    #     sample_flag=True)
    # client.send_event(event)

    # print("Sleeping for 0.5 seconds")
    # time.sleep(0.5)

    # new_events, connected = client.pump()

    # for event in new_events:
    #     print("New event:", event)
            
    
    # print("Connected?", connected)