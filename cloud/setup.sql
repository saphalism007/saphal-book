-- Saphal Book, the one table the server needs.
--
-- Run this once, in the Supabase SQL Editor, on the saphal-book project.
-- Running it twice does no harm.
--
-- What the server is allowed to know, and what it is not.
--
-- It holds a row for each set of books, for each person. In that row is the
-- locked file and nothing else of any use. The name of the company is inside
-- the locked file, not beside it, and the name the row is filed under is not
-- the company slug but a fingerprint of it made with the owner's own key. So
-- somebody reading this table sees a list of meaningless strings against
-- meaningless bytes. That is the whole intention.
--
-- What it does know: how many sets of books somebody keeps, how large each one
-- is, and when each was last changed. There is no way to hide that from a
-- server that has to store and serve them.

create table if not exists public.books (
    owner       uuid        not null references auth.users (id) on delete cascade,

    -- A fingerprint of which set of books this is, made on the device with a
    -- key the server never sees. The same books always give the same
    -- fingerprint, so a device can find them again, and no two people who
    -- happen to name a company the same way collide.
    book_id     text        not null check (char_length(book_id) between 16 and 128),

    -- Counts up by one on every save. A device that has not seen the latest
    -- version is refused, which is what stops a tablet that has been out of
    -- range all day from quietly overwriting a day of counter sales.
    version     bigint      not null default 1 check (version > 0),

    -- The locked file, as text. Unreadable without the owner's password.
    payload     text        not null,

    -- Which device wrote it last, so a person can be told where the newer copy
    -- came from rather than just being told there is one.
    device      text        not null default '',

    updated_at  timestamptz not null default now(),

    primary key (owner, book_id)
);

-- Nothing is readable until a rule says so.
alter table public.books enable row level security;

-- And the only rule is: your own rows, nobody else's, in either direction.
-- The check half matters as much as the using half. Without it somebody could
-- read only their own rows but write rows belonging to anyone.
drop policy if exists "a person reaches only their own books" on public.books;
create policy "a person reaches only their own books"
    on public.books
    for all
    to authenticated
    using (auth.uid() = owner)
    with check (auth.uid() = owner);

-- The project was created with new tables hidden by default, so this table is
-- opened deliberately, and only to people who have signed in. Nothing is
-- granted to anon, which is the key that ships inside the app.
grant select, insert, update, delete on public.books to authenticated;

create index if not exists books_owner_idx on public.books (owner);

-- Keep updated_at honest. A device could otherwise send any time it liked.
create or replace function public.touch_books()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

drop trigger if exists books_touch on public.books;
create trigger books_touch
    before insert or update on public.books
    for each row execute function public.touch_books();
