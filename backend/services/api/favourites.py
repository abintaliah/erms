from fastapi import APIRouter, Depends, HTTPException, Response, status
from psycopg import Connection

from .authentication import Principal, principal_from_request
from .database import get_connection
from .schemas import FavouritesRead


router = APIRouter(prefix="/api/v1/favourites", tags=["favourites"])


@router.get("", response_model=FavouritesRead)
def list_favourites(
    principal: Principal = Depends(principal_from_request),
    connection: Connection = Depends(get_connection, scope="function"),
):
    aggregations = connection.execute(
        """
        SELECT aggregation.id, aggregation.aggregation_number,
               aggregation.title, aggregation.parent_aggregation_id,
               favourite.date_created AS date_favourited
        FROM user_favourite_aggregations favourite
        JOIN aggregations aggregation ON aggregation.id = favourite.aggregation_id
        WHERE favourite.user_id = %s
        ORDER BY favourite.date_created DESC, aggregation.id DESC
        """,
        (principal.user_id,),
    ).fetchall()
    records = connection.execute(
        """
        SELECT record.id, record.record_number, record.title,
               record.aggregation_id, aggregation.aggregation_number,
               aggregation.title AS aggregation_title,
               favourite.date_created AS date_favourited
        FROM user_favourite_records favourite
        JOIN records record ON record.id = favourite.record_id
        JOIN aggregations aggregation ON aggregation.id = record.aggregation_id
        WHERE favourite.user_id = %s
        ORDER BY favourite.date_created DESC, record.id DESC
        """,
        (principal.user_id,),
    ).fetchall()
    return {"aggregations": aggregations, "records": records}


def _add_favourite(
    connection: Connection, principal: Principal, *, table: str,
    target_table: str, target_column: str, target_id: int,
) -> None:
    exists = connection.execute(
        f"SELECT 1 FROM {target_table} WHERE id = %s", (target_id,)
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"{target_table[:-1]} not found")
    connection.execute(
        f"""
        INSERT INTO {table} (user_id, {target_column})
        VALUES (%s, %s)
        ON CONFLICT (user_id, {target_column}) DO NOTHING
        """,
        (principal.user_id, target_id),
    )


def _remove_favourite(
    connection: Connection, principal: Principal, *, table: str,
    target_column: str, target_id: int,
) -> None:
    connection.execute(
        f"DELETE FROM {table} WHERE user_id = %s AND {target_column} = %s",
        (principal.user_id, target_id),
    )


@router.put("/aggregations/{aggregation_id}", status_code=status.HTTP_204_NO_CONTENT)
def favourite_aggregation(
    aggregation_id: int,
    principal: Principal = Depends(principal_from_request),
    connection: Connection = Depends(get_connection, scope="function"),
):
    _add_favourite(
        connection, principal, table="user_favourite_aggregations",
        target_table="aggregations", target_column="aggregation_id",
        target_id=aggregation_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/aggregations/{aggregation_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfavourite_aggregation(
    aggregation_id: int,
    principal: Principal = Depends(principal_from_request),
    connection: Connection = Depends(get_connection, scope="function"),
):
    _remove_favourite(
        connection, principal, table="user_favourite_aggregations",
        target_column="aggregation_id", target_id=aggregation_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def favourite_record(
    record_id: int,
    principal: Principal = Depends(principal_from_request),
    connection: Connection = Depends(get_connection, scope="function"),
):
    _add_favourite(
        connection, principal, table="user_favourite_records",
        target_table="records", target_column="record_id", target_id=record_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfavourite_record(
    record_id: int,
    principal: Principal = Depends(principal_from_request),
    connection: Connection = Depends(get_connection, scope="function"),
):
    _remove_favourite(
        connection, principal, table="user_favourite_records",
        target_column="record_id", target_id=record_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
