"""Unit tests for Package SQL Model."""

import pytest

from core.sql_model.base import SqlObjectType
from core.sql_model.package import Package

pytestmark = [pytest.mark.unit]


class TestPackage:
    """Tests for the Package SQL Model class."""

    def test_package_creation(self):
        """Test basic package creation."""
        package = Package(
            name="employee_pkg",
            schema="hr",
            spec="-- Package spec content",
            body="-- Package body content",
        )

        assert package.name == "employee_pkg"
        assert package.schema == "hr"
        assert package.spec == "-- Package spec content"
        assert package.body == "-- Package body content"
        assert package.object_type == SqlObjectType.PACKAGE
        assert package.dialect == "oracle"

    def test_package_with_minimal_attributes(self):
        """Test package creation with minimal attributes."""
        package = Package(name="simple_pkg")

        assert package.name == "simple_pkg"
        assert package.schema is None
        assert package.spec is None
        assert package.body is None
        assert package.procedures == []
        assert package.functions == []

    def test_package_string_representation(self):
        """Test string representation includes schema and name."""
        package_with_schema = Package(name="pkg", schema="schema1", spec="spec")
        package_without_schema = Package(name="pkg", spec="spec")

        assert "schema1.pkg" in str(package_with_schema)
        assert "pkg" in str(package_without_schema)
        assert "spec only" in str(package_with_schema)

    def test_package_create_statement_with_both(self):
        """Test CREATE statement generation with spec and body."""
        package = Package(
            name="test_pkg",
            schema="hr",
            spec="AS\nPROCEDURE get_emp(id NUMBER);\nEND;",
            body="AS\nPROCEDURE get_emp(id NUMBER) IS\nBEGIN\n  NULL;\nEND;\nEND;",
        )

        stmt = package.create_statement
        assert "CREATE OR REPLACE PACKAGE" in stmt
        assert "hr.test_pkg" in stmt or '"hr"."test_pkg"' in stmt  # Accept quoted or unquoted
        assert "CREATE OR REPLACE PACKAGE BODY" in stmt
        assert stmt.count("\n/") == 2  # Slash terminator for spec and body

    def test_package_create_statement_strips_embedded_create(self):
        """Spec text that already includes CREATE OR REPLACE should not duplicate header."""
        spec = "CREATE OR REPLACE PACKAGE order_notifications AS\n PROCEDURE demo;\nEND order_notifications;\n/"
        package = Package(
            name="order_notifications",
            schema="DBLIFT_TEST",
            spec=spec,
            body="PACKAGE BODY order_notifications AS\n PROCEDURE demo IS BEGIN NULL; END demo;\nEND order_notifications",
        )

        stmt = package.create_statement
        assert stmt.count('CREATE OR REPLACE PACKAGE "DBLIFT_TEST"."order_notifications"') == 1
        assert "CREATE OR REPLACE PACKAGE order_notifications AS" not in stmt
        assert stmt.count("CREATE OR REPLACE PACKAGE BODY") == 1

    def test_package_create_statement_spec_only(self):
        """Test CREATE statement with spec only."""
        package = Package(
            name="test_pkg",
            spec="AS\nPROCEDURE get_emp(id NUMBER);\nEND;",
        )

        stmt = package.create_statement
        assert "CREATE OR REPLACE PACKAGE" in stmt
        assert "test_pkg" in stmt
        assert "CREATE OR REPLACE PACKAGE BODY" not in stmt
        assert stmt.rstrip().endswith("/")

    def test_package_create_statement_body_only(self):
        """Test CREATE statement with body only."""
        package = Package(
            name="test_pkg",
            body="AS\nBEGIN\n  NULL;\nEND;",
        )

        stmt = package.create_statement
        assert "CREATE OR REPLACE PACKAGE BODY" in stmt
        assert "test_pkg" in stmt
        assert stmt.count("CREATE OR REPLACE PACKAGE BODY") == 1
        assert stmt.rstrip().endswith("/")

    def test_package_str_representation(self):
        """Test string representation."""
        pkg_both = Package(name="pkg1", spec="spec", body="body")
        pkg_spec = Package(name="pkg2", spec="spec")
        pkg_body = Package(name="pkg3", body="body")
        pkg_empty = Package(name="pkg4")

        assert "spec + body" in str(pkg_both)
        assert "spec only" in str(pkg_spec)
        assert "body only" in str(pkg_body)
        assert str(pkg_empty) == "Package pkg4"

    def test_package_equality(self):
        """Test package equality comparison."""
        pkg1 = Package(name="pkg", schema="hr", spec="spec1", body="body1")
        pkg2 = Package(name="pkg", schema="hr", spec="spec1", body="body1")
        pkg3 = Package(name="pkg", schema="hr", spec="spec2", body="body1")

        assert pkg1 == pkg2
        assert pkg1 != pkg3
        assert pkg1 != "not a package"

    def test_package_to_dict(self):
        """Test conversion to dictionary."""
        package = Package(
            name="test_pkg",
            schema="hr",
            spec="-- spec",
            body="-- body",
        )
        package.procedures = ["proc1", "proc2"]
        package.functions = ["func1"]

        pkg_dict = package.to_dict()

        assert pkg_dict["name"] == "test_pkg"
        assert pkg_dict["schema"] == "hr"
        assert pkg_dict["object_type"] == "PACKAGE"
        assert pkg_dict["dialect"] == "oracle"
        assert pkg_dict["spec"] == "-- spec"
        assert pkg_dict["body"] == "-- body"
        assert pkg_dict["procedures"] == ["proc1", "proc2"]
        assert pkg_dict["functions"] == ["func1"]

    def test_package_from_dict(self):
        """Test creation from dictionary."""
        pkg_dict = {
            "name": "test_pkg",
            "schema": "hr",
            "spec": "-- spec content",
            "body": "-- body content",
            "dialect": "oracle",
        }

        package = Package.from_dict(pkg_dict)

        assert package.name == "test_pkg"
        assert package.schema == "hr"
        assert package.spec == "-- spec content"
        assert package.body == "-- body content"
        assert package.dialect == "oracle"

    def test_package_round_trip(self):
        """Test to_dict/from_dict round trip."""
        original = Package(
            name="pkg",
            schema="schema1",
            spec="SPEC",
            body="BODY",
        )

        # Round trip
        pkg_dict = original.to_dict()
        restored = Package.from_dict(pkg_dict)

        assert original == restored

    def test_package_without_schema_in_create_statement(self):
        """Test CREATE statement without schema prefix."""
        package = Package(
            name="test_pkg",
            spec="AS\nEND;",
        )

        stmt = package.create_statement
        assert "CREATE OR REPLACE PACKAGE" in stmt
        assert "test_pkg" in stmt
        # Schema prefix should not appear in first line (only package name)
        first_line = stmt.split("\n")[0]
        assert first_line.count(".") == 0 or '"."' not in first_line  # No schema.table pattern

    def test_package_tracks_procedures_and_functions(self):
        """Test that package can track its procedures and functions."""
        package = Package(name="pkg")

        # Initially empty
        assert package.procedures == []
        assert package.functions == []

        # Add some
        package.procedures.append("get_employee")
        package.procedures.append("update_salary")
        package.functions.append("calculate_tax")

        assert len(package.procedures) == 2
        assert len(package.functions) == 1
        assert "get_employee" in package.procedures
        assert "calculate_tax" in package.functions
