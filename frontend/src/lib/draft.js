export function genDraft({ who, need, candidate, lang, intent }) {
  const c = candidate;
  const w = who;
  const n = (need || '').trim();
  const sect = c.sectors.join(lang === 'vi' ? ' và ' : ' and ');
  const person = intent === 'talent';

  if (lang === 'vi') {
    const hi = person ? 'Kính gửi ' + c.name + ',' : 'Kính gửi anh/chị tại ' + c.name + ',';
    const ask = intent === 'talent'
      ? 'Chúng tôi nghĩ bạn rất phù hợp với đội ngũ của ' + w + '.'
      : intent === 'customers'
      ? 'Chúng tôi tin giải pháp của ' + w + ' có thể hỗ trợ nhu cầu của quý vị.'
      : intent === 'investors'
      ? 'Chúng tôi đang tìm nhà đầu tư đồng hành cho vòng gọi vốn.'
      : 'Chúng tôi mong tìm cơ hội hợp tác nghiên cứu và cố vấn cùng quý vị.';
    return 'Chủ đề: ' + w + ' × ' + c.name + '\n\n' + hi + '\n\nTôi liên hệ từ ' + w + '. ' +
      (n || 'Chúng tôi đang xây dựng giải pháp dữ liệu đất cho nông dân Việt Nam.') + '\n\n' +
      ask + ' Với trọng tâm ở lĩnh vực ' + sect + ', quý vị có thể sắp xếp một cuộc trao đổi ngắn trong hai tuần tới không?\n\nTrân trọng,\n' + w;
  }

  const hi = person ? 'Dear ' + c.name + ',' : 'Dear team at ' + c.name + ',';
  const ask = intent === 'talent'
    ? "We think you'd be a great fit for the team at " + w + '.'
    : intent === 'customers'
    ? 'I believe ' + w + " can help with your team's needs."
    : intent === 'investors'
    ? "We're looking for an investor to partner on our round."
    : "We'd love to explore a research and mentorship collaboration.";
  return 'Subject: ' + w + ' × ' + c.name + '\n\n' + hi + "\n\nI'm reaching out from " + w + '. ' +
    (n || 'We are building soil-intelligence tools for Vietnamese farmers.') + '\n\n' +
    ask + ' Given your focus on ' + sect + ', would you be open to a short call in the next two weeks?\n\nWarm regards,\n' + w;
}
