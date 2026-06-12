"""CosmosDB SDK Translator package.

Public API — same as the original cosmosdb_sdk_translator.py module.

    from db.plugins.cosmosdb.sdk_translator import CosmosDbSdkTranslator

Sub-modules
-----------
_translators.py : _CosmosDbTranslatorMixin — all _translate_* and parser helper methods
_executors.py   : _CosmosDbExecutorMixin  — execute_sdk_operation and _execute_* methods
_translator.py  : CosmosDbSdkTranslator  — main class composing the two mixins

Supported Pseudo-SQL Syntax:
----------------------------
Container Operations:
    DROP CONTAINER <name>
    ALTER CONTAINER <name> SET (<property>=<value>, ...)

Throughput Management:
    SET THROUGHPUT ON CONTAINER <name> TO <value>
    SET AUTOSCALE ON CONTAINER <name> MAX <max_throughput> [MIN <min_throughput>]
    SHOW THROUGHPUT ON CONTAINER <name>

Index Management:
    CREATE INDEX <name> ON <container> (<column> [ASC|DESC], ...)
    DROP INDEX <name> ON <container>
    EXCLUDE INDEX PATH '<path>' ON CONTAINER <name>
    INCLUDE INDEX PATH '<path>' ON CONTAINER <name>

TTL Management:
    SET TTL ON CONTAINER <name> TO <seconds>
    SET TTL ON CONTAINER <name> TO OFF
"""

from db.plugins.cosmosdb.sdk_translator._translator import CosmosDbSdkTranslator

__all__ = [
    "CosmosDbSdkTranslator",
]
