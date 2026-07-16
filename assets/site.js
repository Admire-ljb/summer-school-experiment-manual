const toggle = document.getElementById('menu-toggle');
if (toggle) {
  toggle.addEventListener('click', () => document.body.classList.toggle('nav-open'));
}

const search = document.getElementById('doc-search');
const navItems = Array.from(document.querySelectorAll('#nav-list li'));
if (search) {
  search.addEventListener('input', () => {
    const query = search.value.trim().toLowerCase();
    navItems.forEach((item) => {
      const text = item.textContent.toLowerCase();
      item.classList.toggle('hidden-by-search', query && !text.includes(query));
    });
  });
}

const isZh = document.documentElement.lang.toLowerCase().startsWith('zh');
const languageSwitch = document.querySelector('.language-switch');
if (languageSwitch && !languageSwitch.querySelector('.page-affiliation')) {
  const options = document.createElement('div');
  options.className = 'language-options';
  Array.from(languageSwitch.children).forEach((child) => options.appendChild(child));

  const affiliation = document.createElement('div');
  affiliation.className = 'page-affiliation';
  const emblem = document.createElement('img');
  emblem.src = '../assets/images/beihang-university-emblem.png';
  emblem.alt = isZh ? '北京航空航天大学校徽' : 'Beihang University emblem';
  emblem.width = 48;
  emblem.height = 48;

  const copy = document.createElement('span');
  copy.className = 'page-affiliation-copy';
  const groupName = document.createElement('strong');
  groupName.textContent = 'ADMIRE Group';
  const university = document.createElement('small');
  university.textContent = isZh ? '北京航空航天大学' : 'Beihang University';
  copy.append(groupName, university);
  affiliation.append(emblem, copy);
  languageSwitch.append(affiliation, options);
}

const content = document.querySelector('.rst-content');
if (content && !content.querySelector('.manual-credit')) {
  const footer = document.createElement('footer');
  footer.className = 'manual-credit';

  const affiliation = document.createElement('div');
  const affiliationName = document.createElement('strong');
  affiliationName.textContent = isZh ? '北航 ADMIRE 组' : 'BUAA ADMIRE Group';
  const affiliationDetail = document.createElement('span');
  affiliationDetail.textContent = isZh ? '北京航空航天大学' : 'Beihang University';
  affiliation.append(affiliationName, affiliationDetail);

  const author = document.createElement('div');
  const authorName = document.createElement('span');
  authorName.textContent = isZh ? '编写者：楼嘉彬 · Lou Jiabin' : 'Author: 楼嘉彬 · Lou Jiabin';
  const email = document.createElement('a');
  email.href = 'mailto:loujiabin@buaa.edu.cn';
  email.textContent = 'loujiabin@buaa.edu.cn';
  author.append(authorName, email);
  footer.append(affiliation, author);
  content.appendChild(footer);
}

document.querySelectorAll('pre code').forEach((code) => {
  const pre = code.parentElement;
  if (!pre || pre.querySelector('.copy-code')) return;
  pre.classList.add('has-copy-button');
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'copy-code';
  button.textContent = isZh ? '复制' : 'Copy';
  button.setAttribute('aria-label', isZh ? '复制代码' : 'Copy code');
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(code.textContent);
      button.textContent = isZh ? '已复制' : 'Copied';
    } catch (error) {
      const range = document.createRange();
      range.selectNodeContents(code);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = isZh ? '请按 Ctrl+C' : 'Press Ctrl+C';
    }
    setTimeout(() => {
      button.textContent = isZh ? '复制' : 'Copy';
    }, 1600);
  });
  pre.appendChild(button);
});
