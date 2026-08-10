\getenv target_user TARGET_POSTGRES_USER
\getenv target_password TARGET_POSTGRES_PASSWORD

SELECT format(
    'ALTER ROLE %I WITH PASSWORD %L',
    :'target_user',
    :'target_password'
) \gexec
