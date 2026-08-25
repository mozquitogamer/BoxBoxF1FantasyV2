-- Repair for migration 005's chip-code validation alias typo.
--
-- 005 is corrected for fresh installs. This append-only patch is for a
-- production database where 005 already created save_member_team_v2 before
-- the endpoint exposed the runtime error. It reuses PostgreSQL's stored
-- function definition, changes only the missing JSONB alias, and is safe to
-- rerun or apply after a corrected 005 (where it becomes a no-op).

begin;

do $$
declare
    v_definition text;
    v_patched text;
begin
    select pg_get_functiondef(
        'public.save_member_team_v2(smallint, text, text, numeric, numeric, numeric, smallint, jsonb, jsonb, smallint, smallint, boolean)'::regprocedure
    )
    into v_definition;

    if v_definition is null then
        raise exception 'public.save_member_team_v2 is missing; apply migration 005 first.';
    end if;

    v_patched := regexp_replace(
        v_definition,
        $patch$from[[:space:]]+jsonb_array_elements\(p_chips\)\)$patch$,
        $patch$from jsonb_array_elements(p_chips) item)$patch$,
        'g'
    );

    if v_patched <> v_definition then
        execute v_patched;
    elsif position('count(distinct item ->> ''chip_code'') from jsonb_array_elements(p_chips) item' in v_definition) = 0 then
        raise exception 'Could not verify the save_member_team_v2 chip alias repair.';
    end if;
end;
$$;

commit;
