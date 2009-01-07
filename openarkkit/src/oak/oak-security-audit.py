#!/usr/bin/python

#
# Audit a server's accounts and privileges
#
# Released under the BSD license
#
# Copyright (c) 2008, Shlomi Noach
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#     * Neither the name of the organization nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

import getpass
import MySQLdb
from optparse import OptionParser


def parse_options():
    parser = OptionParser()
    parser.add_option("-u", "--user", dest="user", default="", help="MySQL user")
    parser.add_option("-H", "--host", dest="host", default="localhost", help="MySQL host (default: localhost)")
    parser.add_option("-p", "--password", dest="password", default="", help="MySQL password")
    parser.add_option("--ask-pass", action="store_true", dest="prompt_password", help="Prompt for password")
    parser.add_option("-P", "--port", dest="port", type="int", default="3306", help="TCP/IP port (default: 3306)")
    parser.add_option("-S", "--socket", dest="socket", default="/var/run/mysqld/mysql.sock", help="MySQL socket file. Only applies when host is localhost")
    parser.add_option("", "--defaults-file", dest="defaults_file", default="", help="Read from MySQL configuration file. Overrides all other options")
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="Print user friendly messages")
    parser.add_option("--print-only", action="store_true", dest="print_only", help="Do not execute. Only print statement")
    return parser.parse_args()

def verbose(message):
    if options.verbose:
        print "-- %s" % message

def verbose_topic(message):
    verbose("")
    verbose(message)
    verbose("-"*len(message))

def recommend(message):
    verbose(message+". Recommended actions:")

def print_error(message):
    print "-- ERROR: %s" % message

def get_in_query(list):
    return "(" + ", ".join([ "'%s'" % item for item in list ]) + ")"
    
def open_connection():
    if options.defaults_file:
        conn = MySQLdb.connect(read_default_file = options.defaults_file)
    else:
        if options.prompt_password:
            password=getpass.getpass()
        else:
            password=options.password
        conn = MySQLdb.connect(
            host = options.host,
            user = options.user,
            passwd = password,
            port = options.port,
            unix_socket = options.socket)
    return conn;

def act_final_query(query):        
    """
    Either print or execute the given query
    """
    if options.print_only:
        print query
    else:
        update_cursor = conn.cursor()
        try:
            try:
                update_cursor.execute(query)
            except:
                print_error("error executing: %s" % query)
        finally:
            update_cursor.close()

def audit_root_user(conn):
    verbose_topic("Looking for non local 'root' accounts")
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT user,host FROM mysql.user WHERE user='root' AND host NOT IN ('localhost', '127.0.0.1')")
    rows = cursor.fetchall()
    if rows:
        recommend("Found %d non local 'root' accounts" % len(rows))
        for row in rows:
            try:
                user, host = row["user"], row["host"]
                query = "DROP USER '%s'@'%s';" % (user, host,)
                print query
            except:
                print_error("-- Cannot %s" % query)
    else:
        verbose("No remote 'root' accouts found")
    cursor.close()

def audit_anonymous_user(conn):
    verbose_topic("Looking for anonymous user accounts")
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT user,host FROM mysql.user WHERE user=''")
    rows = cursor.fetchall()
    if rows:
        recommend("Found %d non anonymous accounts" % len(rows))
        for row in rows:
            try:
                user, host = row["user"], row["host"]
                query = "DROP USER '%s'@'%s';" % (user, host,)
                print query
            except:
                print_error("-- Cannot %s" % query)
    else:
        verbose("No anonymous accounts found")
    cursor.close()

def audit_any_host(conn):
    verbose_topic("Looking for accounts accessible from any host")
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT user,host FROM mysql.user WHERE host='%'")
    rows = cursor.fetchall()
    if rows:
        recommend("Found %d accounts accessible from any host" % len(rows))
        for row in rows:
            try:
                user, host = row["user"], row["host"]
                query = "RENAME USER '%s'@'%s' TO '%s'@'<specific host>';" % (user, host, user,)
                print query
            except:
                print_error("-- Cannot %s" % query)
    else:
        verbose("No wildcard hosts found")
    cursor.close()

def audit_empty_passwords_accounts(conn):
    verbose_topic("Looking for accounts with empty passwords")
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT user,host FROM mysql.user WHERE password=''")
    rows = cursor.fetchall()
    if rows:
        recommend("Found %d accounts with empty passwords" % len(rows))
        for row in rows:
            try:
                user, host = row["user"], row["host"]
                new_password = '<some password>'
                
                query = "SET PASSWORD FOR '%s'@'%s' = PASSWORD('%s');" % (user, host, new_password)
                print query
            except:
                print_error("-- Cannot %s" % query)
    else:
        verbose("No empty password accounts found")
    cursor.close()

def audit_identical_passwords_accounts(conn):
    verbose_topic("Looking for accounts with identical (non empty) passwords")
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT CONCAT('''', user, '''@''', host, '''' ) AS account, pass FROM (SELECT user1.user, user1.host, user2.user AS u2, user2.host AS h2, left(user1.password,5) as pass FROM mysql.user AS user1 INNER JOIN mysql.user AS user2 ON (user1.password = user2.password) WHERE user1.user != user2.user AND user1.password != '') users GROUP BY (CONCAT(user,'@',host)) ORDER BY pass")
    rows = cursor.fetchall()
    if rows:
        passwords = set([row["pass"] for row in rows])
        verbose("There are %d groups of accounts sharing the same passwords" % len(passwords))
        for password in passwords:
            accounts = [row["account"] for row in rows if row['pass'] == password]
            recommend("The following accounts have different users yet share the same password: %s" % ", ".join(accounts))
            for account in accounts:
                new_password = '<some passowrd>'
                query = "SET PASSWORD FOR %s = PASSWORD('%s');" % (account, new_password)
                print query
    else:
        verbose("No empty password accounts found")
    cursor.close()


def audit_all_privileges(conn):
    verbose_topic("Looking for (non root) accounts with all privileges")
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT user,host FROM mysql.user ORDER BY user,host")

    permissive_privileges = []
    for row in cursor.fetchall():
        try:
            user, host = row["user"], row["host"]

            query = "SHOW GRANTS FOR '%s'@'%s'" % (user, host,)
            grant_cursor = conn.cursor()
            grant_cursor.execute(query)
            grants = grant_cursor.fetchall()

            for grant in [grantrow[0] for grantrow in grants]:
                if grant.startswith("GRANT ALL PRIVILEGES ON *.* TO") and user != "root":
                    query = "GRANT <specific privileges> ON *.* TO '%s'@'%s';" % (user, host,)
                    permissive_privileges.append((user,host,query,))
            grant_cursor.close()
            
        except:
            print "-- Cannot %s" % query
    if permissive_privileges:
        verbose("There are %d non root accounts with all privileges" % len(permissive_privileges))
        for (user,host,query) in permissive_privileges:
            print query 
    else:
        verbose("No accounts found with all privileges")
       
    cursor.close()


def audit_admin_privileges(conn):
    verbose_topic("Looking for (non-root) accounts with admin privileges")
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)
    query = "SELECT GRANTEE, GROUP_CONCAT(PRIVILEGE_TYPE) AS privileges FROM information_schema.USER_PRIVILEGES WHERE PRIVILEGE_TYPE IN %s GROUP BY GRANTEE" % get_in_query(privileges_admin)
    cursor.execute(query)

    grantees = [row["GRANTEE"] for row in cursor.fetchall()]
    suspicious_grantees = [grantee for grantee in grantees if not grantee.startswith("'root'")]

    if suspicious_grantees:
        verbose("There are %d non-root accounts with admin privileges" % len(suspicious_grantees))
        recommend("admin privileges are: %s" % ", ".join(privileges_admin))
        for grantee in suspicious_grantees:
            query = "GRANT <non-admin-privileges> ON *.* TO %s;" % grantee
            print query
    else:
        verbose("No accounts found with admin privileges")
       
    cursor.close()


def audit_sql_mode(conn):
    verbose_topic("Checking global sql_mode")
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT @@sql_mode AS sql_mode")
    sql_mode = cursor.fetchone()["sql_mode"]

    NO_AUTO_CREATE_USER = "NO_AUTO_CREATE_USER"
    if NO_AUTO_CREATE_USER in sql_mode.split(","):
        verbose("sql_mode is good")
    else:
        recommend("sql_mode does not contain %s" % NO_AUTO_CREATE_USER)
        desired_sql_mode = NO_AUTO_CREATE_USER
        if sql_mode:
            desired_sql_mode += ","+sql_mode
        query = "SET GLOBAL sql_mode = '%s';" % desired_sql_mode
        print query
    
def audit_old_passwords(conn):
    verbose_topic("Checking old_passwords setting")
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT @@old_passwords AS old_passwords")
    old_passwords = int(cursor.fetchone()["old_passwords"])

    if old_passwords:
        recommend("Old passwords are being used")
        verbose("Consider removing old-passwords from configuration. Make sure you read the manual first")
    else:
        verbose("New passwords are used.")
    cursor.close()
    
def audit_skip_networking(conn):
    verbose_topic("Checking networking")
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SHOW GLOBAL VARIABLES LIKE 'skip_networking'")
    value = cursor.fetchone()['Value']
    if value == 'OFF':
        recommend("Networking is enabled")
        verbose("This is usually fine. If you're only accessing MySQL from the localhost,")
        verbose("consider setting --skip-networking and using UNIX socket or named pipes.")
    else:
        verbose("Networking is disabled")

    cursor.close()
    
def audit_test_database(conn):
    verbose_topic("Checking for `test` database existance")
    cursor = conn.cursor()
    cursor.execute("SHOW DATABASES")
    rows = cursor.fetchall()
    if 'test' in [row[0] for row in rows]:
        recommend("`test` database found")
        query = "DROP DATABASE test;"
        print query
    else:
        verbose("`test` database not found")

    cursor.close()


try:
    try:
        privileges_admin = ["SUPER", "SHUTDOWN", "RELOAD", "PROCESS", "CREATE USER", "REPLICATION CLIENT", "REPLICATION SLAVE", ]
        privileges_extreme_dml = ["CREATE", "DROP", "EVENT", "ALTER", "INDEX", "TRIGGER", "CREATE VIEW", "ALTER ROUTINE", "CREATE ROUTINE", ]
        privileges_dml = ["DELETE", "INSERT", "UPDATE", "CREATE TEMPORARY TABLES", ]
        conn = None
        (options, args) = parse_options()
        conn = open_connection()
        
        audit_root_user(conn)
        audit_anonymous_user(conn)
        audit_any_host(conn)
        
        audit_empty_passwords_accounts(conn)
        audit_identical_passwords_accounts(conn)
        
        audit_all_privileges(conn)
        audit_admin_privileges(conn)
        
        audit_sql_mode(conn)
        audit_old_passwords(conn)
        audit_skip_networking(conn)        
        audit_test_database(conn)
        
    except Exception, err:
        print err[-1]
finally:
    if conn:
        conn.close()