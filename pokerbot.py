import datetime
import time
import socketio
import requests
import sys
import re  # For parsing messages

sio = socketio.Client()
session = requests.Session()

Users = {}
my_id = ""
pid = ""
api = ""
anon_name = "Spy"

seen = {}
awaiting_hand = False  # To track if we are waiting for a hand
awaiting_result = False  # To track if we are waiting for a result
bet_amount = 0  # Variable to store the bet amount

def upd_seen(username):
    seen[username] = datetime.datetime.now().strftime("%H:%M:%S")

def get_bet():
    global bet_amount
    while True:
        try:
            bet_input = input("What do you want to bet? Enter a number: ")
            bet_amount = int(bet_input)
            if bet_amount <= 0:
                print("Bet must be a positive number.")
            else:
                break
        except ValueError:
            print("Please enter a valid number.")

def main():
    global api, awaiting_hand
    server = "play.gikopoi.com"
    area = "for"
    room = "bar"
    character = "akai"
    name = input("Enter your username: ")
    password = "akai"

    if len(sys.argv) > 1:
        room = sys.argv[1]

    if "poipoi" in server:
        api = "/api"

    # Ask for the bet before connecting
    get_bet()

    logon(server, area, room, character, name, password)

    print([Users[u] for u in Users])

    # Start poker automation with the bet amount
    send_message(f"!poker {bet_amount}")
    awaiting_hand = True

    while True:
        val = input()
        if len(val):
            if val[0] == ",":
                move_around(val[1:])
            else:
                sio.emit("user-msg", val)
        else:
            sio.emit("user-msg", val)

def logon(server, area, room, character, name, password):
    global my_id, pid
    url = "https://" + server
    wss = "ws://" + server + ":8085/socket.io/"
    print("[+] Connect")
    connect_value = {
        "userName": name,
        "characterId": character,
        "areaId": area,
        "roomId": room,
        "password": password
    }
    connect_response = session.post(f"{url}{api}/login", connect_value)
    connect_json = connect_response.json()
    if not connect_json['isLoginSuccessful']:
        print("Not able to login")
        return

    print("[+] Connected")
    my_id = str(connect_json['userId'])
    pid = str(connect_json['privateUserId'])
    version = str(connect_json["appVersion"])

    sio.connect(wss, headers={"private-user-id": pid})
    get_users(session, url, area, room)

def get_users(s: requests.Session, server, area, room):
    print("[+] Get Rooms Users")
    val = s.get(f'{server}{api}/areas/{area}/rooms/{room}',
                headers={"Authentication": f"Bearer {pid}"})
    if val.status_code == 200:
        users = val.json()['connectedUsers']
        for user in users:
            Users[user['id']] = user['name'] or anon_name
            if Users[user['id']].strip():
                upd_seen(Users[user['id']])

def send_message(msg):
    sio.emit("user-msg", msg)
    sio.emit("user-msg", "")

@sio.event
def connect():
    print("[+] I'm connected!")

@sio.event
def disconnect():
    print("I'm disconnected!")

@sio.on('server-msg')
def server_msg(event, namespace):
    author = get_username(event)
    if author == "":
        author = anon_name
    if event == my_id:
        return
    if len(namespace) == 0:
        return

    tstamp = datetime.datetime.now().strftime("%H:%M")
    print('{} < {} > {}'.format(tstamp, author, namespace))

    # Check if the message is from giko.py
    if author == "giko.py":
        handle_giko_message(namespace)

def handle_giko_message(msg):
    global awaiting_hand, awaiting_result

    # Detect poker hand message
    hand_match = re.search(f"{Users.get(my_id, anon_name)}'s hand is now \((.*?)\)", msg)
    if hand_match and not awaiting_result:
        hand = hand_match.group(1)
        print(f"Current hand: {hand}")
        if awaiting_hand:
            time.sleep(1)  # Wait for 1 second before discarding cards
            discard_cards(hand)
            awaiting_hand = False
            awaiting_result = True
        return

    # Detect result message
    if "Congrats" in msg or "lost" in msg:
        print(f"Game result detected: {msg}")
        awaiting_result = False
        time.sleep(1)  # Add delay before sending the next !poker
        send_message(f"!poker {bet_amount}")
        awaiting_hand = True

from collections import Counter

def discard_cards(hand):
    # Split the hand into cards
    cards = hand.split("/")

    # Separate the ranks and suits
    ranks = [card[1:] for card in cards]  # Extract ranks (the part after the suit)
    suits = [card[0] for card in cards]  # Extract suits (the first character)

    # Count occurrences of each rank
    rank_counts = Counter(ranks)

    drop_indices = []

    # Check for Royal Flush (A-K-Q-J-10 all in same suit)
    royal_flush = ["10", "J", "Q", "K", "A"]
    if all(rank in ranks for rank in royal_flush) and len(set(suits)) == 1:
        print("Royal Flush detected, keeping the hand!")
        drop_indices = []  # Don't drop any cards
        drop_command = "!drop 0"
        print(f"Discarding cards: {drop_command}")
        send_message(drop_command)
        return

    # Check for Straight Flush (five consecutive cards in same suit)
    sorted_ranks = sorted([int(r) if r.isdigit() else {'J': 11, 'Q': 12, 'K': 13, 'A': 14}[r] for r in ranks])
    if len(set(suits)) == 1 and len(sorted_ranks) == 5 and sorted_ranks == list(range(sorted_ranks[0], sorted_ranks[0] + 5)):
        print("Straight Flush detected, keeping the hand!")
        drop_indices = []  # Don't drop any cards
        drop_command = "!drop 0"
        print(f"Discarding cards: {drop_command}")
        send_message(drop_command)
        return

    # Check for Four of a Kind
    four_of_a_kind_rank = None
    for rank, count in rank_counts.items():
        if count == 4:
            four_of_a_kind_rank = rank
            break

    if four_of_a_kind_rank:
        print("Four of a Kind detected, keeping the hand!")
        drop_indices = []  # Don't drop any cards
        drop_command = "!drop 0"
        print(f"Discarding cards: {drop_command}")
        send_message(drop_command)
        return

    # Check for Full House (three of one rank, two of another)
    if len(rank_counts) == 2 and sorted(rank_counts.values()) == [2, 3]:
        print("Full House detected, keeping the hand!")
        drop_indices = []  # Don't drop any cards
        drop_command = "!drop 0"
        print(f"Discarding cards: {drop_command}")
        send_message(drop_command)
        return

    # Check for Flush (five cards of the same suit, not in sequence)
    if len(set(suits)) == 1:
        print("Flush detected, keeping the hand!")
        drop_indices = []  # Don't drop any cards
        drop_command = "!drop 0"
        print(f"Discarding cards: {drop_command}")
        send_message(drop_command)
        return

    # Check for Straight (five consecutive cards, not necessarily in the same suit)
    sorted_ranks = sorted([int(r) if r.isdigit() else {'J': 11, 'Q': 12, 'K': 13, 'A': 14}[r] for r in ranks])
    if len(sorted_ranks) == 5 and sorted_ranks == list(range(sorted_ranks[0], sorted_ranks[0] + 5)):
        print("Straight detected, keeping the hand!")
        drop_indices = []  # Don't drop any cards
        drop_command = "!drop 0"
        print(f"Discarding cards: {drop_command}")
        send_message(drop_command)
        return

    # Check for Two Pairs
    pairs = [rank for rank, count in rank_counts.items() if count == 2]

    if len(pairs) == 2:
        # If there are two pairs, discard the single card left not matching
        print("Two pairs detected, discarding the non-pair card.")
        for i, card in enumerate(cards):
            if ranks[i] not in pairs:  # If the card is not part of the two pairs
                drop_indices.append(str(i + 1))  # Add index to drop
    else:
        # Check if there's a Three of a Kind
        three_of_a_kind_rank = None
        for rank, count in rank_counts.items():
            if count == 3:
                three_of_a_kind_rank = rank
                break

        if three_of_a_kind_rank:
            # If Three of a Kind is detected, discard the other cards
            for i, card in enumerate(cards):
                if ranks[i] != three_of_a_kind_rank:  # If the card is not part of the Three of a Kind
                    drop_indices.append(str(i + 1))  # Add index to drop
        else:
            # If no Three of a Kind, drop non-face cards (2-10)
            for i, card in enumerate(cards):
                rank = ranks[i]
                if rank not in ["J", "Q", "K", "A"]:
                    drop_indices.append(str(i + 1))  # Add index to drop

    # If the hand is made entirely of face cards, discard all non-preferred cards
    face_cards = ["J", "Q", "K", "A"]
    if all(rank in face_cards for rank in ranks):
        print("Hand is made entirely of face cards, discarding non-preferred cards.")
        # Determine the most frequent rank(s) to keep
        max_count = max(rank_counts.values())
        preferred_cards = [rank for rank, count in rank_counts.items() if count == max_count]

        # Discard all cards that are not in the preferred ranks
        for i, rank in enumerate(ranks):
            if rank not in preferred_cards:
                drop_indices.append(str(i + 1))  # Add index to drop

    # Prepare the drop command
    if drop_indices:
        drop_command = "!drop " + " ".join(drop_indices)
        print(f"Discarding cards: {drop_command}")
        send_message(drop_command)


def get_username(userid):
    return Users.get(userid, anon_name)

def move_around(directions):
    uplr = {"u": "up", "d": "down", "l": "left", "r": "right"}
    directions = list(directions)
    for d in directions:
        if d in uplr:
            sio.emit("user-move", uplr[d])

# Poker hand evaluation functions
def is_straight(cards):
    value_map = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

    ranks = [card[:-1] for card in cards]  # Remove the last character (suit)
    try:
        values = sorted([value_map[v] for v in ranks])
    except KeyError as e:
        print(f"KeyError: {e} - Invalid rank found in cards: {ranks}")
        return False

    return values == list(range(values[0], values[0] + 5))

def is_flush(cards):
    suits = [card[-1] for card in cards]  # Get the suit (last character) of each card
    return len(set(suits)) == 1  # If all suits are the same, it's a flush

def is_straight_flush(cards):
    return is_straight(cards) and is_flush(cards)

def is_royal_flush(cards):
    value_map = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

    ranks = [card[:-1] for card in cards]
    try:
        values = sorted([value_map[v] for v in ranks])
    except KeyError as e:
        print(f"KeyError: {e} - Invalid rank found in cards: {ranks}")
        return False

    return values == [10, 11, 12, 13, 14] and is_flush(cards)

def is_full_house(cards):
    ranks = [card[:-1] for card in cards]
    rank_counts = {rank: ranks.count(rank) for rank in ranks}
    return sorted(rank_counts.values()) == [2, 3]  # A full house has one pair and one three-of-a-kind

def is_four_of_a_kind(cards):
    ranks = [card[:-1] for card in cards]
    rank_counts = {rank: ranks.count(rank) for rank in ranks}
    return 4 in rank_counts.values()  # A four-of-a-kind has four of the same rank

def is_three_of_a_kind(cards):
    ranks = [card[:-1] for card in cards]
    rank_counts = {rank: ranks.count(rank) for rank in ranks}
    return 3 in rank_counts.values()  # A three-of-a-kind has three of the same rank

if __name__ == "__main__":
    awaiting_hand = True  # Start with awaiting the first hand
    main()