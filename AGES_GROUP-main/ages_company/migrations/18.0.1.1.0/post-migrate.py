# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Move legacy single Old/New account fields into mapping lines."""
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'ages_sub_company'
           AND column_name IN ('old_account_id', 'new_account_id')
        """
    )
    columns = {row[0] for row in cr.fetchall()}
    if 'old_account_id' not in columns or 'new_account_id' not in columns:
        return

    cr.execute(
        """
        INSERT INTO ages_sub_company_account_mapping (
            sub_company_id,
            company_id,
            old_account_id,
            new_account_id,
            create_uid,
            create_date,
            write_uid,
            write_date
        )
        SELECT
            sc.id,
            sc.company_id,
            sc.old_account_id,
            sc.new_account_id,
            sc.create_uid,
            NOW() AT TIME ZONE 'UTC',
            sc.write_uid,
            NOW() AT TIME ZONE 'UTC'
        FROM ages_sub_company sc
        WHERE sc.old_account_id IS NOT NULL
          AND sc.new_account_id IS NOT NULL
          AND NOT EXISTS (
                SELECT 1
                  FROM ages_sub_company_account_mapping m
                 WHERE m.sub_company_id = sc.id
                   AND m.old_account_id = sc.old_account_id
          )
        """
    )
