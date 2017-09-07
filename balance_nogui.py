import sqlite3, keys

(key, private_key_readable, public_key_readable, public_key_hashed, address) = keys.read()

mempool = sqlite3.connect('mempool.db')
mempool.text_factory = str
m = mempool.cursor()

# include mempool fees
m.execute("SELECT count(amount), sum(amount) FROM transactions WHERE address = ?;", (address,))
result = m.fetchall()[0]
if result[1] != None:
    debit_mempool = float(result[1]) + float(result[1]) * 0.001 + int(result[0]) * 0.01
else:
    debit_mempool = 0
# include mempool fees

conn = sqlite3.connect('static/ledger.db')
conn.text_factory = str
c = conn.cursor()
c.execute("SELECT sum(amount) FROM transactions WHERE recipient = ?;", (address,))
credit = c.fetchone()[0]
c.execute("SELECT sum(amount) FROM transactions WHERE address = ?;", (address,))
debit = c.fetchone()[0]
c.execute("SELECT sum(fee) FROM transactions WHERE address = ?;", (address,))
fees = c.fetchone()[0]
c.execute("SELECT sum(reward) FROM transactions WHERE address = ?;", (address,))
rewards = c.fetchone()[0]
c.execute("SELECT MAX(block_height) FROM transactions")
bl_height = c.fetchone()[0]

debit = 0 if debit is None else debit
fees = 0 if fees is None else fees
rewards = 0 if rewards is None else rewards
credit = 0 if credit is None else credit

balance = credit - debit - fees + rewards - debit_mempool

print("Public key address: {}".format(address))
print("Total fees paid: {}".format(fees))
print("Total rewards mined: {}".format(rewards))
print("Total tokens received: {}".format(credit))
print("Total tokens spent: {}".format(debit))
print("Transction address balance: {}".format(balance))
