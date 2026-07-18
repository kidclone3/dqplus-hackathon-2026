import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import AppHeader from '../components/AppHeader';
import Screen from '../components/Screen';
import { Card, Dot, Eyebrow, PrimaryButton, SecondaryButton, SerifHeading, StatusPill } from '../components/ui';
import { useApp } from '../context/AppContext';
import { SECTORS } from '../data/mockData';
import { colors, fonts, spacing } from '../theme/theme';
import { addReceivedCard, loadReceivedCards } from '../services/storage';
import { isNfcAvailable, scanProfileFromNfc, shareProfileViaNfc } from '../services/nfc';

const sectorLabel = (id) => SECTORS.find((s) => s.id === id)?.label || id;

export default function ProfileCardScreen({ navigation }) {
  const { accent, role, isInvestor, form, status, whoName } = useApp();
  const [nfcSupported, setNfcSupported] = useState(null);
  const [shareStatus, setShareStatus] = useState('');
  const [scanStatus, setScanStatus] = useState('');
  const [busy, setBusy] = useState(null); // 'share' | 'scan' | null
  const [receivedCards, setReceivedCards] = useState([]);

  useEffect(() => {
    let cancelled = false;
    isNfcAvailable().then((ok) => { if (!cancelled) setNfcSupported(ok); });
    loadReceivedCards().then((list) => { if (!cancelled) setReceivedCards(list); });
    return () => { cancelled = true; };
  }, []);

  const payload = {
    v: 1,
    role: role || 'startup',
    name: whoName,
    website: form.website,
    stage: form.stage,
    geography: form.geography,
    sectorLabels: form.sectors.map(sectorLabel),
    need: form.need,
    traction: form.traction,
  };

  const onShare = async () => {
    setBusy('share');
    setShareStatus('Hold your phone near a writable NFC tag…');
    try {
      await shareProfileViaNfc(payload);
      setShareStatus('Shared to tag ✓');
    } catch (e) {
      setShareStatus(e.message || 'Could not write to that tag.');
    } finally {
      setBusy(null);
    }
  };

  const onScan = async () => {
    setBusy('scan');
    setScanStatus('Hold your phone near a shared card…');
    try {
      const card = await scanProfileFromNfc();
      const next = await addReceivedCard(card);
      setReceivedCards(next);
      setScanStatus(`Imported ${card.name || 'a card'} ✓`);
    } catch (e) {
      setScanStatus(e.message || 'Could not read that tag.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <AppHeader />
      <Screen>
        <Pressable onPress={() => navigation.goBack()}>
          <Text style={styles.backLink}>← Back</Text>
        </Pressable>

        <Eyebrow style={{ marginTop: 20 }}>Your card</Eyebrow>
        <SerifHeading style={{ marginTop: 12 }}>{whoName}</SerifHeading>
        <View style={styles.metaRow}>
          <Dot color={isInvestor ? '#7a5aa6' : '#3f8f6b'} />
          <Text style={styles.metaType}>{isInvestor ? 'Investor' : 'Startup'}</Text>
          <StatusPill ready={status === 'ready'} accent={accent} />
        </View>

        {form.website ? <Text style={styles.website}>{form.website}</Text> : null}

        {form.sectors.length ? (
          <View style={styles.sectorWrap}>
            {form.sectors.map((id) => (
              <View key={id} style={styles.sectorPill}>
                <Text style={styles.sectorText}>{sectorLabel(id)}</Text>
              </View>
            ))}
          </View>
        ) : null}

        <Card style={{ marginTop: spacing.xl }}>
          <Text style={styles.sectionEyebrow}>{isInvestor ? 'Stage focus' : 'Stage'} · Geography</Text>
          <Text style={styles.plainText}>
            {(form.stage || '—')}{'  ·  '}{(form.geography || '—')}
          </Text>
        </Card>

        {form.need ? (
          <Card style={{ marginTop: 14 }}>
            <Text style={styles.sectionEyebrow}>{isInvestor ? 'Collaboration need' : 'Funding need'}</Text>
            <Text style={styles.plainText}>{form.need}</Text>
          </Card>
        ) : null}

        {form.traction ? (
          <Card style={{ marginTop: 14 }}>
            <Text style={styles.sectionEyebrow}>Traction</Text>
            <Text style={styles.plainText}>{form.traction}</Text>
          </Card>
        ) : null}

        <Card style={{ marginTop: spacing.xl }}>
          <Text style={styles.sectionEyebrow}>Share via NFC</Text>
          <Text style={styles.helperText}>
            {nfcSupported === false
              ? 'NFC isn’t available here — it needs a custom Expo dev build on a physical Android/iOS device, not Expo Go or web.'
              : 'Tap to write your card to an NFC tag, or scan a tag someone else shared.'}
          </Text>
          <View style={styles.actionsRow}>
            <PrimaryButton
              label={busy === 'share' ? 'Sharing…' : 'Share via NFC'}
              onPress={onShare}
              accent={accent}
              disabled={busy !== null || nfcSupported === false}
              style={{ flex: 1 }}
            />
            <SecondaryButton
              label={busy === 'scan' ? 'Scanning…' : 'Scan a card'}
              onPress={onScan}
              style={{ flex: 1 }}
            />
          </View>
          {shareStatus ? <Text style={styles.statusText}>{shareStatus}</Text> : null}
          {scanStatus ? <Text style={styles.statusText}>{scanStatus}</Text> : null}
        </Card>

        {receivedCards.length ? (
          <Card style={{ marginTop: 14 }}>
            <Text style={styles.sectionEyebrow}>Received via NFC</Text>
            <View style={{ marginTop: 10, gap: 10 }}>
              {receivedCards.map((c, i) => (
                <View key={`${c.name}-${i}`} style={styles.receivedRow}>
                  <Dot color={c.role === 'investor' ? '#7a5aa6' : '#3f8f6b'} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.receivedName}>{c.name || 'Unnamed'}</Text>
                    <Text style={styles.receivedMeta}>
                      {(c.role === 'investor' ? 'Investor' : 'Startup')}
                      {c.sectorLabels && c.sectorLabels.length ? ' · ' + c.sectorLabels.join(', ') : ''}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          </Card>
        ) : null}
      </Screen>
    </View>
  );
}

const styles = StyleSheet.create({
  backLink: { color: colors.textFaint, fontSize: 12.5, fontFamily: fonts.sans },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 14 },
  metaType: { color: colors.textFaint, fontSize: 12.5, fontFamily: fonts.sansMedium },
  website: { marginTop: 10, color: colors.accent, fontSize: 14, fontFamily: fonts.sansMedium },
  sectorWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginTop: 14 },
  sectorPill: {
    paddingVertical: 5, paddingHorizontal: 11, borderWidth: 1, borderColor: colors.border,
    borderRadius: 99, backgroundColor: colors.card,
  },
  sectorText: { color: colors.textMuted, fontSize: 12, fontFamily: fonts.sans },
  sectionEyebrow: { color: colors.textFaint, fontSize: 11.5, letterSpacing: 0.5, textTransform: 'uppercase', fontFamily: fonts.sansSemiBold },
  plainText: { marginTop: 10, color: colors.textBody, fontSize: 14.5, lineHeight: 22, fontFamily: fonts.sans },
  helperText: { marginTop: 10, color: colors.textMuted, fontSize: 13.5, lineHeight: 20, fontFamily: fonts.sans },
  actionsRow: { flexDirection: 'row', gap: 10, marginTop: 16 },
  statusText: { marginTop: 12, color: colors.textFaint, fontSize: 12.5, fontFamily: fonts.sans },
  receivedRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  receivedName: { color: colors.label, fontSize: 14, fontFamily: fonts.sansSemiBold },
  receivedMeta: { color: colors.textFaint, fontSize: 12.5, fontFamily: fonts.sans, marginTop: 2 },
});
