#!/usr/bin/env perl
use strict;
use warnings;
use JSON::PP;
use File::Spec;
use File::Basename;
use File::Path qw(make_path);

my $data = $ENV{QUOTA_DATA_DIR} // '/app/quota_lab';
my $audit = $ENV{QUOTA_AUDIT_DIR} // '/app/audit';
make_path($audit);

my $json = JSON::PP->new->canonical(1)->pretty(1);

sub read_json {
    my ($path) = @_;
    open my $fh, '<', $path or die $!;
    local $/;
    return $json->decode(<$fh>);
}

my $policy = read_json(File::Spec->catfile($data, 'policy.json'));
my $events = read_json(File::Spec->catfile($data, 'events.json'));
my $day = $policy->{audit_day};
my @order = @{ $policy->{tier_order} };
my %caps = %{ $policy->{tier_caps} };
$_ = int($_) for values %caps;

for my $d (@{ $events->{tier_derates} // [] }) {
    next unless $d->{start_day} <= $day && $day <= $d->{end_day};
    my $t = $d->{tier};
    $caps{$t} = int($caps{$t} * $d->{factor_bp} / 10000) if exists $caps{$t};
}

my %frozen;
for my $f (@{ $events->{item_freezes} // [] }) {
    $frozen{ $f->{item_id} } = 1 if $f->{start_day} <= $day && $day <= $f->{end_day};
}

sub tier_key {
    my ($tier) = @_;
    for my $i (0 .. $#order) {
        return ($i, $tier) if $order[$i] eq $tier;
    }
    return (scalar @order, $tier);
}

my @items;
opendir my $dh, File::Spec->catdir($data, 'items') or die $!;
for my $f (sort grep { /\.json\z/ } readdir $dh) {
    push @items, read_json(File::Spec->catfile($data, 'items', $f));
}
closedir $dh;
@items = sort {
    my ($ra, $ta) = tier_key($a->{tier});
    my ($rb, $tb) = tier_key($b->{tier});
    $ra <=> $rb || $ta cmp $tb || $a->{item_id} cmp $b->{item_id};
} @items;

my %tier_rem = %caps;
my @rows;
my %sc = (frozen => 0, ok => 0, shortfall => 0);

for my $it (@items) {
    my ($iid, $tier, $demand) = ($it->{item_id}, $it->{tier}, int($it->{demand}));
    if ($frozen{$iid}) {
        push @rows, { item_id => $iid, tier => $tier, status => 'frozen', demand => $demand, allocated => 0 };
        $sc{frozen}++;
        next;
    }
    my $left = $tier_rem{$tier} // 0;
    my $alloc = $demand < $left ? $demand : $left;
    $tier_rem{$tier} = $left - $alloc;
    my $st = $alloc == $demand ? 'ok' : 'shortfall';
    $sc{$st}++;
    push @rows, { item_id => $iid, tier => $tier, status => $st, demand => $demand, allocated => $alloc };
}

my %seen;
my @touched = sort grep { !$seen{$_}++ } map { $_->{tier} } grep { $_->{allocated} > 0 } @rows;

my $summary = {
    audit_day       => $day,
    items_processed => scalar @items,
    frozen_items    => $sc{frozen},
    status_counts   => \%sc,
    tiers_touched   => \@touched,
};

sub write_json {
    my ($path, $obj) = @_;
    open my $fh, '>', $path or die $!;
    print {$fh} $json->encode($obj), "\n";
}

write_json(File::Spec->catfile($audit, 'allocations.json'), { items => \@rows });
write_json(File::Spec->catfile($audit, 'summary.json'), $summary);
