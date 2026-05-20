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

create table if not exists wa_sessions (
  id uuid primary key default gen_random_uuid(),
  instance_name text not null default 'RTEPORT_INSTANTANEO',
  admin_phone text not null,
  step text not null default 'idle',
  selected_group_jid text,
  selected_group_name text,
  pending_groups jsonb,
  updated_at timestamptz not null default now(),
  unique (instance_name, admin_phone)
);

create table if not exists wa_summaries (
  id uuid primary key default gen_random_uuid(),
  instance_name text not null default 'RTEPORT_INSTANTANEO',
  group_jid text not null,
  group_name text,
  summary_date date not null,
  content text not null,
  message_count int default 0,
  requested_by text,
  sent_to_group boolean default false,
  poll_sent boolean default false,
  created_at timestamptz not null default now(),
  unique (instance_name, group_jid, summary_date)
);

create index if not exists idx_wa_sessions_admin on wa_sessions (admin_phone);
create index if not exists idx_wa_summaries_group on wa_summaries (group_jid, summary_date desc);

alter table wa_sessions enable row level security;
alter table wa_summaries enable row level security;
