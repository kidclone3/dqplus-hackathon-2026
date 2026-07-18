import { Platform } from 'react-native';

// react-native-nfc-manager is a native module: it only works in a custom
// Expo dev build (after `expo prebuild`), never in Expo Go and never on web.
// Every entry point below lazily requires it and swallows load/native errors
// so the rest of the app keeps working when NFC hardware/build isn't present.
function loadNfcManager() {
  if (Platform.OS === 'web') return null;
  try {
    return require('react-native-nfc-manager');
  } catch (e) {
    return null;
  }
}

export async function isNfcAvailable() {
  const mod = loadNfcManager();
  if (!mod) return false;
  try {
    const NfcManager = mod.default;
    await NfcManager.start();
    return await NfcManager.isSupported();
  } catch (e) {
    return false;
  }
}

export async function shareProfileViaNfc(payload) {
  const mod = loadNfcManager();
  if (!mod) throw new Error('NFC is not available on this device/build.');
  const { default: NfcManager, NfcTech, Ndef } = mod;
  try {
    await NfcManager.requestTechnology(NfcTech.Ndef);
    const bytes = Ndef.encodeMessage([Ndef.textRecord(JSON.stringify(payload))]);
    await NfcManager.writeNdefMessage(bytes);
  } finally {
    NfcManager.cancelTechnologyRequest().catch(() => {});
  }
}

export async function scanProfileFromNfc() {
  const mod = loadNfcManager();
  if (!mod) throw new Error('NFC is not available on this device/build.');
  const { default: NfcManager, NfcTech, Ndef } = mod;
  try {
    await NfcManager.requestTechnology(NfcTech.Ndef);
    const tag = await NfcManager.getTag();
    const record = tag && tag.ndefMessage && tag.ndefMessage[0];
    if (!record) throw new Error('No profile data found on this tag.');
    const text = Ndef.text.decodePayload(Uint8Array.from(record.payload));
    return JSON.parse(text);
  } finally {
    NfcManager.cancelTechnologyRequest().catch(() => {});
  }
}
