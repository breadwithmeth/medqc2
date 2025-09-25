# -*- coding: utf-8 -*-

# Grammar-ограничение (если решите включать грамматику вместо JSON-Schema)
AUDIT_JSON_GBNF = r"""
root        ::= ws obj ws

obj         ::= "{" ws "\"passes\"" ws ":" ws arr_items ws "," ws "\"violations\"" ws ":" ws arr_items ws "," ws "\"assessed_rule_ids\"" ws ":" ws arr_strings ws "}"

arr_items   ::= "[" ws (item (ws "," ws item)*)? ws "]"
arr_strings ::= "[" ws (jstring (ws "," ws jstring)*)? ws "]"

item        ::= "{" ws
                 "\"rule_id\""      ws ":" ws jstring ws "," ws
                 "\"title\""        ws ":" ws jstring ws "," ws
                 "\"severity\""     ws ":" ws severity ws "," ws
                 "\"required\""     ws ":" ws jbool   ws "," ws
                 "\"order\""        ws ":" ws jstring ws "," ws
                 "\"where\""        ws ":" ws jstring ws "," ws
                 "\"evidence\""     ws ":" ws jstring
               ws "}"

severity    ::= "\"critical\"" | "\"major\"" | "\"minor\""

jbool       ::= "true" | "false"

jstring     ::= "\"" jchar* "\""
jchar       ::= [^"\\] | ("\\" ("\"" | "\\" | "/" | "b" | "f" | "n" | "r" | "t"))

ws          ::= ([ \t\n\r])*
"""
