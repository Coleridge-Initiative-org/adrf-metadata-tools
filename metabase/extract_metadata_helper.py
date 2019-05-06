"""Helper funtions for extract_metadata.
"""

from collections import namedtuple, Counter
import getpass
import json
import os
import statistics

import psycopg2
from psycopg2 import sql


def get_column_type(data_cursor, col, categorical_threshold, schema_name,
                    table_name, date_format_dict):
    """Return the column type and the contents of the column."""

    col_type = ''
    data = []

    numeric_flag, numeric_data = is_numeric(data_cursor, col, schema_name,
                                            table_name)
    date_flag, date_data = is_date(data_cursor, col, schema_name, table_name,
                                   date_format_dict)
    code_flag, code_data = is_code(data_cursor, col, schema_name, table_name,
                                   categorical_threshold)

    if numeric_flag:
        col_type = 'numeric'
        data = numeric_data
    elif date_flag:
        col_type = 'date'
        data = date_data
    elif code_flag:
        col_type = 'code'
        data = code_data
    else:
        col_type = 'text'
        data = code_data  # If is_code is False, column assumed to be text.

    column_data = namedtuple('column_data', ['type', 'data'])
    return column_data(col_type, data)


def is_numeric(data_cursor, col, schema_name, table_name):
    """Return True and contents of column if column is numeric.
    """

    try:
        data_cursor.execute(
            sql.SQL("""
            SELECT {}::NUMERIC FROM {}.{}
            """).format(
                sql.Identifier(col),
                sql.Identifier(schema_name),
                sql.Identifier(table_name),
            )
        )
        data = [i[0] for i in data_cursor.fetchall()]
        flag = True
    except (psycopg2.ProgrammingError, psycopg2.DataError):
        data_cursor.execute('DROP TABLE IF EXISTS converted_data')
        data = []
        flag = False

    return flag, data


def is_date(data_cursor, col, schema_name, table_name, date_format_dict):
    """
    Return True and contents of column if column is date.

    Note that date format for each column can be configured in the config file.
    If the format of a temporal column is not specified, Metabase will try to
    convert the column into dates appropriately. If this process fails or a
    column cannot be converted into date with the configured date formatting,
    that column will be identified as a textual column instead.
    """
    if col in date_format_dict:
        try:
            # TODO: Replace the trial with a rigid date parser

            data_cursor.execute(
                sql.SQL("""
                    SELECT
                        CASE WHEN {} IS NOT NULL THEN TO_DATE({}::TEXT, %s)
                        -- First convert into TEXT in case that column is
                        -- in DATE type.
                        ELSE NULL END
                    FROM {}.{}
                """).format(
                    sql.Identifier(col),
                    sql.Identifier(col),
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                ),
                [date_format_dict[col]],
            )
            data = [i[0] for i in data_cursor.fetchall()]
            flag = True
        except (psycopg2.ProgrammingError, psycopg2.DataError):
            data = []
            flag = False

    else:
        # col not in date_format_dict or date_format_dict is not provided
        # Try to parse dates with the default method.
        try:
            data_cursor.execute(
                sql.SQL("""
                    SELECT {}::DATE FROM {}.{}
                """).format(
                    sql.Identifier(col),
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                )
            )
            data = [i[0] for i in data_cursor.fetchall()]
            flag = True
        except (psycopg2.ProgrammingError, psycopg2.DataError):
            data = []
            flag = False

    return flag, data


def is_code(data_cursor, col, schema_name, table_name,
            categorical_threshold):
    """Return True and contents of column if column is categorical.
    """

    data_cursor.execute(
        sql.SQL(
            """
            SELECT COUNT(DISTINCT {}) FROM {}.{}
            """).format(
            sql.Identifier(col),
            sql.Identifier(schema_name),
            sql.Identifier(table_name),
        )
    )
    n_distinct = data_cursor.fetchall()[0][0]

    data_cursor.execute(sql.SQL("""
        SELECT {} FROM {}.{}
        """).format(
                sql.Identifier(col),
                sql.Identifier(schema_name),
                sql.Identifier(table_name),
        )
        )
    data = [i[0] for i in data_cursor.fetchall()]

    if n_distinct <= categorical_threshold:
        flag = True
    else:
        flag = False

    return flag, data


def update_numeric(metabase_cursor, col_name, col_data, data_table_id):
    """Update Column Info and Numeric Column for a numerical column."""

    serial_column_id = update_column_info(metabase_cursor, col_name,
                                          data_table_id, 'numeric')
    # TODO: Update created by, created date.

    numeric_stats = get_numeric_metadata(col_data)

    metabase_cursor.execute(
        """
        INSERT INTO metabase.numeric_column (
            column_id,
            data_table_id,
            column_name,
            minimum,
            maximum,
            mean,
            median,
            updated_by,
            date_last_updated
        ) VALUES (
            %(column_id)s,
            %(data_table_id)s,
            %(column_name)s,
            %(minimum)s,
            %(maximum)s,
            %(mean)s,
            %(median)s,
            %(updated_by)s,
            (SELECT CURRENT_TIMESTAMP)
        )
        """,
        {
            'column_id': serial_column_id,
            'data_table_id': data_table_id,
            'column_name': col_name,
            'minimum': numeric_stats.min,
            'maximum': numeric_stats.max,
            'mean': numeric_stats.mean,
            'median': numeric_stats.median,
            'updated_by': getpass.getuser(),
        }
    )


def get_numeric_metadata(col_data):
    """Get metdata from a numeric column."""

    not_null_num_ls = [num for num in col_data if num is not None]

    if not_null_num_ls:
        mean = statistics.mean(not_null_num_ls)
        median = statistics.median(not_null_num_ls)
        max_col = max(not_null_num_ls)
        min_col = min(not_null_num_ls)
    else:
        mean = None
        median = None
        max_col = None
        min_col = None

    numeric_stats = namedtuple(
        'numeric_stats',
        ['min', 'max', 'mean', 'median'],
    )
    return numeric_stats(min_col, max_col, mean, median)


def update_text(metabase_cursor, col_name, col_data, data_table_id):
    """Update Column Info  and Numeric Column for a text column."""

    serial_column_id = update_column_info(metabase_cursor, col_name,
                                          data_table_id, 'text')
    # Update created by, created date.

    (max_len, min_len, median_len) = get_text_metadata(col_data)

    metabase_cursor.execute(
        """
        INSERT INTO metabase.text_column
        (
        column_id,
        data_table_id,
        column_name,
        max_length,
        min_length,
        median_length,
        updated_by,
        date_last_updated
        )
        VALUES
        (
        %(column_id)s,
        %(data_table_id)s,
        %(column_name)s,
        %(max_length)s,
        %(min_length)s,
        %(median_length)s,
        %(updated_by)s,
        (SELECT CURRENT_TIMESTAMP)
        )
        """,
        {
            'column_id': serial_column_id,
            'data_table_id': data_table_id,
            'column_name': col_name,
            'max_length': max_len,
            'min_length': min_len,
            'median_length': median_len,
            'updated_by': getpass.getuser(),
        }
    )


def get_text_metadata(col_data):
    """Get metadata from a text column."""

    not_null_text_ls = [text for text in col_data if text is not None]

    if not_null_text_ls:
        text_lens_ls = [len(text) for text in not_null_text_ls]
        min_len = min(text_lens_ls)
        max_len = max(text_lens_ls)
        median_len = statistics.median(text_lens_ls)
    else:
        # Will only be needed if categorical_threshold = 0
        min_len = None
        max_len = None
        median_len = None

    return (max_len, min_len, median_len)


def update_date(metabase_cursor, col_name, col_data,
                data_table_id):
    """
    Update Column Info and Date Column for a date column.
    """
    serial_column_id = update_column_info(metabase_cursor, col_name,
                                          data_table_id, 'date')

    (minimum, maximum) = get_date_metadata(col_data)

    metabase_cursor.execute(
        """
        INSERT INTO metabase.date_column
        (
        column_id,
        data_table_id,
        column_name,
        min_date,
        max_date,
        updated_by,
        date_last_updated
        )
        VALUES
        (
        %(column_id)s,
        %(data_table_id)s,
        %(column_name)s,
        %(min_date)s,
        %(max_date)s,
        %(updated_by)s,
        (SELECT CURRENT_TIMESTAMP)
        )
        """,
        {
            'column_id': serial_column_id,
            'data_table_id': data_table_id,
            'column_name': col_name,
            'min_date': minimum,
            'max_date': maximum,
            'updated_by': getpass.getuser(),
        }
        )


def get_date_metadata(col_data):
    """Get metadata from a date column."""

    not_null_date_ls = [date for date in col_data if date is not None]

    if not_null_date_ls:
        min_date = min(not_null_date_ls)
        max_date = max(not_null_date_ls)
    else:
        min_date = None
        max_date = None

    return (min_date, max_date)


def update_code(metabase_cursor, col_name, col_data,
                data_table_id):
    """Update Column Info and Code Frequency for a categorical column."""

    serial_column_id = update_column_info(metabase_cursor, col_name,
                                          data_table_id, 'code')

    code_counter = get_code_metadata(col_data)

    for code, frequency in code_counter.items():
        metabase_cursor.execute(
            """
            INSERT INTO metabase.code_frequency (
                column_id,
                data_table_id,
                column_name,
                code,
                frequency,
                updated_by,
                date_last_updated
            ) VALUES (
                %(column_id)s,
                %(data_table_id)s,
                %(column_name)s,
                %(code)s,
                %(frequency)s,
                %(updated_by)s,
               (SELECT CURRENT_TIMESTAMP)
            )
            """,
            {
                'column_id': serial_column_id,
                'data_table_id': data_table_id,
                'column_name': col_name,
                'code': code,
                'frequency': frequency,
                'updated_by': getpass.getuser(),
            },
        )


def get_code_metadata(col_data):

    code_frequecy_counter = Counter(col_data)

    return code_frequecy_counter


def update_column_info(cursor, col_name, data_table_id, data_type):
    """Add a row for this data column to the column info metadata table."""

    # TODO How to handled existing rows?

    # Create Column Info entry
    cursor.execute(
        """
        INSERT INTO metabase.column_info (
            data_table_id,
            column_name,
            data_type,
            updated_by,
            date_last_updated
        )
        VALUES (
            %(data_table_id)s,
            %(column_name)s,
            %(data_type)s,
            %(updated_by)s,
            (SELECT CURRENT_TIMESTAMP)
        )
        RETURNING column_id
        ;
        """,
        {
            'data_table_id': data_table_id,
            'column_name': col_name,
            'data_type': data_type,
            'updated_by': getpass.getuser(),
        }
    )

    serial_column_id = cursor.fetchall()[0][0]
    return serial_column_id


# #############################################################################
#   Called by `ExtractMetadata.export_table_metadata()`
# #############################################################################

def select_table_level_gmeta_fields(metabase_cur, data_table_id):
    """
    Select metadata at data set and table levels.
    """
    date_format_str = 'YYYY-MM-DD'

    metabase_cur.execute(
        """
            SELECT
                file_table_name AS file_name,
                format AS file_type,
                data_table.data_set_id AS dataset_id,
                -- data_set.title AS title,
                -- data_set.description AS description,
                TO_CHAR(start_date, %(date_format_str)s)
                    AS temporal_coverage_start,
                TO_CHAR(end_date, %(date_format_str)s)
                    AS temporal_coverage_end,
                -- geographical_coverage
                -- geographical_unit
                -- data_set.keywords AS keywords,
                -- data_set.category AS category,
                -- data_set.document_link AS reference_url,
                contact AS data_steward,
                -- data_set.data_set_contact AS data_steward_organization,
                size::FLOAT AS file_size
                -- number_rows AS rows    NOTE: not included in the sample file
                -- number_columns AS columns
                --   NOTE: not included in the sample file
            FROM metabase.data_table
                -- JOIN metabase.data_set USING (data_set_id)
            WHERE data_table_id = %(data_table_id)s
        """,
        {
            'date_format_str': date_format_str,
            'data_table_id': data_table_id
        },
    )

    return metabase_cur.fetchall()[0]
    # Index by 0 since the result is a list of one dict.


def select_column_level_gmeta_fields(metabase_cur, data_table_id):
    """
    Select column-level metadata. Gmeta fields to export are different by
    column type.
    """
    metabase_cur.execute(
        """
            SELECT column_id, column_name, data_type
            FROM metabase.column_info
            WHERE data_table_id = %(data_table_id)s;
        """,
        {
            'data_table_id': data_table_id,
        },
    )

    column_id_name_type_tp_ls = metabase_cur.fetchall()

    column_gmeta_fields_dict = {}

    for column_id, column_name, data_type in column_id_name_type_tp_ls:
        if data_type == 'numeric':
            column_gmeta_fields_dict[
                (column_id, column_name, 'Numeric')
                # Links Metabase data type terms to Gmeta terms.
                # E.g. `text` in Metabase is `Textual` in Gmeta.
            ] = select_numeric_gmeta_fields(
                metabase_cur,
                column_id,
            )

        elif data_type == 'date':
            column_gmeta_fields_dict[
                (column_id, column_name, 'Temporal')
            ] = select_temporal_gmeta_fields(
                metabase_cur,
                column_id,
            )

        elif data_type == 'code':
            # TODO: Categorical type is not presented in the Gmeta sample.
            # Currently treated the same as Textual columns.
            column_gmeta_fields_dict[
                (column_id, column_name, 'Categorical')
            ] = select_categorical_gmeta_fields(
                metabase_cur,
                column_id,
            )

        else:
            # data_type = 'text':
            column_gmeta_fields_dict[
                (column_id, column_name, 'Textual')
            ] = select_textual_gmeta_fields(
                metabase_cur,
                column_id,
            )

    return column_gmeta_fields_dict


def select_numeric_gmeta_fields(metabase_cur, column_id):
    """
    Select Gmeta fields related to numerical columns.
    """
    metabase_cur.execute(
        """
            SELECT
                minimum::FLOAT AS min,
                maximum::FLOAT AS max,
                mean::FLOAT
                -- Without type cast it will return in Decimal('#')

            FROM metabase.numeric_column
            WHERE column_id = %(column_id)s
        """,
        {
            'column_id': column_id,
        },
    )

    result = metabase_cur.fetchall()
    if result:
        return result[0]
    else:
        return None


def select_temporal_gmeta_fields(metabase_cur, column_id):
    """
    Select Gmeta fields related to temporal columns.
    """
    metabase_cur.execute(
        """
            SELECT
                TO_CHAR(min_date, 'MM/DD/YYYY HH:MM:SS AM') AS min,
                TO_CHAR(max_date, 'MM/DD/YYYY HH:MM:SS AM') AS max
            FROM metabase.date_column
            WHERE column_id = %(column_id)s
        """,
        {
            'column_id': column_id,
        },
    )

    result = metabase_cur.fetchall()
    if result:
        return result[0]
    else:
        return None


def select_categorical_gmeta_fields(metabase_cur, column_id):
    """
    Select Gmeta fields related to categorical columns.

    Note that the return value is different from other column types.

    Args:
        metabase_cur
        column_id

    Return:
        (Query result object fetched from psycopg2's DictCursor):
            Like a list of dictionaries with column names as keys. An empty
            list is returned if no record to fetch.
    """
    metabase_cur.execute(
        """
            SELECT code, frequency
            FROM metabase.code_frequency
            WHERE column_id = %(column_id)s
            ORDER BY frequency DESC
            LIMIT 20    -- Top-k
        """,
        {
            'column_id': column_id,
        },
    )

    return metabase_cur.fetchall()


def select_textual_gmeta_fields(metabase_cur, column_id):
    """
    Select Gmeta fields related to textual columns.
    """
    metabase_cur.execute(
        # Placeholder query for now
        """
            SELECT
                max_length::FLOAT
            FROM metabase.text_column
            WHERE column_id = %(column_id)s
        """,
        {
            'column_id': column_id,
        },
    )

    result = metabase_cur.fetchall()
    if result:
        return result[0]
    else:
        return None


def export_gmeta_in_json(table_gmeta_dict, column_gmeta_dict, output_filepath):
    """
    Shape and export GMETA fields in JSON format.
    """
    columns_metadata_dict = {}

    for ((_column_id, column_name, data_type),
         column_result) in column_gmeta_dict.items():
        if column_result:
            if data_type == 'Numeric':
                columns_metadata_dict[column_name] = {
                    'profiler-type': data_type,
                    'profiler-most-detected': None,
                    'missing': None,
                    'values': None,
                    'min': column_result['min'],
                    'max': column_result['max'],
                    'std': None,
                    'mean': column_result['mean'],
                    'Histogram Data JSON': {},
                    'top-k': {},
                    'top-value': None,
                    'freq-top-value': None,
                    'description': None,
                }

            elif data_type == 'Temporal':
                columns_metadata_dict[column_name] = {
                    'profiler-type': data_type,
                    'profiler-most-detected': None,
                    'missing': None,
                    'values': None,
                    'min': column_result['min'],
                    'max': column_result['max'],
                    'std': None,
                    'mean': None,
                    'top-k': {},
                    'top-value': None,
                    'freq-top-value': None,
                    'description': None,
                }

            elif data_type == 'Categorical':
                top_k_dict = {}
                for row_dict in column_result:
                    top_k_dict[row_dict['code']] = row_dict['frequency']

                columns_metadata_dict[column_name] = {
                    'profiler-type': data_type,
                    'profiler-most-detected': None,
                    'missing': None,
                    'values': None,
                    'top-k': top_k_dict,
                    'top-value': column_result[0]['code'],
                    'freq-top-value': column_result[0]['frequency'],
                    'description': None,
                }

            else:
                # data_type == 'Textual':
                columns_metadata_dict[column_name] = {
                    'profiler-type': data_type,
                    'profiler-most-detected': None,
                    'missing': None,
                    'values': None,
                    'top-k': {},
                    'top-value': None,
                    'freq-top-value': None,
                    'description': None,
                }

    output_table_gmeta_dict = {
        'file_name': table_gmeta_dict['file_name'],
        'columns_metadata': columns_metadata_dict,
        'file_type': table_gmeta_dict['file_type'],
        'file_size': table_gmeta_dict['file_size'],
        'mimetype': None,
    }

    output_dict = {
        'gmeta': [{
            table_gmeta_dict['file_name']: {
                'mimetype': 'application/json',
                'content': {
                    'dataset_id': None,
                    'temporal_coverage_start': None,
                    'temporal_coverage_end': None,
                    'files_total': 1,
                    'data_classification': None,
                    'access_actions_required': None,
                    'geographical_coverage': [],
                    'keywords': [],
                    'category': None,
                    'dataset_version': None,
                    'title': None,
                    'data_usage_policy': None,
                    'data_steward_organization': None,
                    'data_steward': None,
                    'files': [
                        output_table_gmeta_dict,
                    ],
                    'access_requirements': None,
                    'description': None,
                    'source_url': None,
                    'geographical_unit': [],
                    'related_articles': [],
                    'data_provider': None,
                    'dataset_documentation': [],
                    'dataset_version_date': None,
                    # In Unix time. E.g. 1541527053
                    'source_archive': None,
                    'dataset_citation': None,
                    'reference_url': None,
                    'file_names': [table_gmeta_dict['file_name']],
                },
                'visible_to': [],
            },
        }],
    }

    try:
        with open(output_filepath, 'w') as output_file:
            json.dump(output_dict, output_file, indent=4)

    except Exception as e:
        if os.path.exists(output_filepath):
            os.remove(output_filepath)

        raise e
