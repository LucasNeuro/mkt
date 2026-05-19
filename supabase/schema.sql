-- Execute no SQL Editor do Supabase (projeto do Report)

create table if not exists wa_groups (
  id uuid primary key default gen_random_uuid(),
  instance_name text not null default 'RTEPORT_INSTANTANEO',
  group_jid text not null,
  group_name text,
  monitor boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (instance_name, group_jid)
);

create table if not exists wa_messages (
  id uuid primary key default gen_random_uuid(),
  instance_name text not null,
  group_jid text not null,
  message_id text not null,
  chat_id text,
  sender_jid text,
  sender_name text,
  text_content text,
  message_type text,
  from_me boolean not null default false,
  raw_payload jsonb,
  message_at timestamptz,
  created_at timestamptz not null default now(),
  unique (instance_name, message_id)
);

create index if not exists idx_wa_messages_group_jid on wa_messages (group_jid);
create index if not exists idx_wa_messages_message_at on wa_messages (message_at desc nulls last);
create index if not exists idx_wa_messages_group_at on wa_messages (group_jid, message_at desc nulls last);

-- API usa service_role no servidor (Render). RLS opcional para leitura via dashboard.
alter table wa_groups enable row level security;
alter table wa_messages enable row level security;
