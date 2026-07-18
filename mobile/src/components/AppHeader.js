import { useNavigation } from '@react-navigation/native';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useApp } from '../context/AppContext';
import { colors, fonts } from '../theme/theme';
import { StatusPill } from './ui';

export default function AppHeader() {
  const { accent, status, authEmail, logout } = useApp();
  const insets = useSafeAreaInsets();
  const navigation = useNavigation();

  return (
    <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
      <View style={styles.brandRow}>
        <View style={[styles.logo, { backgroundColor: accent }]}>
          <Text style={styles.logoText}>V</Text>
        </View>
        <Text style={styles.brandName}>VietNexus</Text>
        <Pressable onPress={() => navigation.navigate('ProfileCard')} style={styles.cardLink}>
          <Text style={[styles.cardLinkText, { color: accent }]}>Your card</Text>
        </Pressable>
      </View>
      <View style={styles.rightRow}>
        <StatusPill ready={status === 'ready'} accent={accent} />
        <Text style={styles.email} numberOfLines={1}>{authEmail || 'founder@startup.vn'}</Text>
        <Pressable onPress={logout} style={styles.logoutBtn}>
          <Text style={styles.logoutText}>Log out</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSoft,
    backgroundColor: colors.bg,
    gap: 10,
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexShrink: 1 },
  cardLink: { marginLeft: 2 },
  cardLinkText: { fontSize: 12.5, fontFamily: fonts.sansSemiBold },
  logo: { width: 28, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  logoText: { color: '#fff', fontFamily: fonts.sansSemiBold, fontSize: 14 },
  brandName: { color: colors.text, fontFamily: fonts.sansSemiBold, fontSize: 15, letterSpacing: -0.2 },
  rightRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexShrink: 1 },
  email: { color: colors.textFaintest, fontSize: 12, flexShrink: 1 },
  logoutBtn: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 9,
    backgroundColor: colors.card,
  },
  logoutText: { color: colors.textMuted, fontSize: 12.5, fontFamily: fonts.sansMedium },
});
