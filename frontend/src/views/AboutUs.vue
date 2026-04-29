<template>
  <div class="about-us">
    <header class="header">
      <h1>CompassFXPluse<br>关于我们</h1>
      <p>了解我们的团队和使命</p>
    </header>

    <section class="mission">
      <h2>我们的使命</h2>
      <p>
        <span style="font-size: x-large;">CompassFXPulse—— 全币种汇率风控与决策支持平台，旨在解决汇率风险管理与决策难题。面对全球外汇市场信息繁杂、汇率风险预测困难以及现有外汇金融服务产品存在诸多不足的现状，本平台依托先进技术，构建了全面且高效的汇率风险防控与决策支持体系。</span>
        <br><br><span style="font-size: x-large;">平台致力于为企业、金融机构及投资者等各类市场参与者，提供一站式的全币种汇率风险防控与决策支持服务。通过整合多源数据，运用前沿模型，解决传统外汇市场交易中数据获取与分析、风险预测及信息服务等方面的难题。</span>
        <br><br><span style="font-size: x-large;">CompassFXPulse 具有广阔的应用前景与市场价值。一方面，平台实现了全币种汇率风险的实时精准预测与高效管理，在风险预测的准确性、时效性以及信息服务的全面性方面，成熟度较高，为用户提供了极具价值的风险管理工具，有效降低汇率波动带来的风险。另一方面，通过创新的智能交互与个性化服务，将外汇金融服务从传统的数据查询与简单分析模式，转变为深度理解用户需求、智能生成决策支持的模式，帮助用户从繁杂的数据处理中解脱出来，专注于核心的外汇交易决策与战略规划，推动外汇金融服务行业向智能化、专业化方向发展。</span>
      </p>
    </section>

    <section class="team">
      <h2>我们的团队</h2>
      <div class="team-members">
        <div class="member" v-for="member in teamMembers" :key="member.name" :class="{'highlight-teacher': member.role === '指导老师'}">
          <img :src="member.image" alt="Team Member" class="member-image">
          <h3>{{ member.name }}</h3>
          <p>{{ member.role }}</p>
          <p>{{ member.bio }}</p>
        </div>
      </div>
    </section>

    <footer class="footer">
      <p>&copy; 2025 Our Company. All rights reserved.</p>
    </footer>
  </div>
</template>

<script>
export default {
  name: 'AboutUs',
  data() {
    return {
      teamMembers: [
        {
          name: '毛韵鉴',
          role: '团队组长',
          bio: '东南大学经济管理学院金融工程专业大三本科生，花旗杯竞赛组长。统筹管理商业组、算法组、软件组协同运作，负责项目整体规划、跨组资源协调及 BP 与技术文档的质量把控。具备扎实的量化研究能力与团队领导力，期待在花旗杯舞台以科技与金融融合的创新思维，展现项目的商业价值与社会影响力。',
          image: require('@/assets/毛韵鉴.png')
        },
        {
          name: '郭皓晨',
          role: '指导老师',
          bio: '东南大学副教授，南京市玄武区科创金融智库专家，从事金融智能、数字金融、金融科技与量化、金融安全与金融风险管理、金融工程等相关领域的交叉研究。具备丰富的金融行业研究经验，擅长将前沿金融理论与实践相结合，致力于培养学生的创新实践能力，推动金融科技应用落地。',
          image: require('@/assets/teacher.png')
        },
        {
          name: '应皓恬',
          role: '商业组组长',
          bio: '东南大学经济管理学院金融学大三本科生，曾荣获校级三好学生、EMBA校友奖学金、至善学子奖学金、社会工作优秀奖等荣誉。积极参与各类科研竞赛，主持一项国家级大学生科研训练项目和一项省级社科联。积极参与商赛、创新创业比赛并多次获奖，产出两篇核心论文。在花旗杯团队中担任商业组组长。',
          image: require('@/assets/应皓恬.png')
        },
        {
          name: '万梓凯',
          role: '软件组组长',
          bio: '东南大学软件工程大三本科生，积极参与过各类相关竞赛。有着丰富的客户端应用、Web应用、小程序开发经验，熟练掌握软件开发技术栈，在本次花旗杯团队中担任软件组组长。',
          image: require('@/assets/万梓凯.png')
        },
        {
          name: '王润哲',
          role: '大语言模型负责人',
          bio: '23级东南大学计算机学院计算机技术专业硕士，研究方向为自然语言处理，大语言模型。曾多次在国际会议上发表工作，并以第一作者身份发表CCF-B类会议论文一篇。在上届花旗杯中作为队长带领队伍获得三等奖，本次作为算法组骨干负责大语言模型相关工作。',
          image: require('@/assets/王润哲.png')
        },
        {
          name: '葛宇超',
          role: '算法组组长',
          bio: '东南大学计算机科学与技术大三本科生。参加过加州大学伯克利分校的交换学习并有过一段在小米公司开发嵌入式软件的实习。在上一届“花旗杯”竞赛随团队中取得全国前20的成绩。',
          image: require('@/assets/葛宇超.png')
        }
      ]
    };
  }
};
</script>

<style scoped>
.about-us {
  background-image:url('~@/assets/white.png'); 
  background-size: cover;
  background-color: aliceblue;
  background-position: center;
  background-repeat: no-repeat;
  overflow: hidden; 
  height: 180vh;
  margin-top: 0%;
  z-index: 10;
  font-family: Arial, sans-serif;
  color: #333;
}

.header {
  background-color: #f8f9fa;
  padding: 20px;
  text-align: center;
}

.header h1 {
  font-size: 2em;
  margin-bottom: 0;
}

.header p {
  font-size: 1.2em;
}

.mission,
.team {
  padding: 20px;
}

.mission h2,
.team h2 {
  font-size: 1.8em;
  margin-bottom: 10px;
}

.team-members {
  display: flex;
  justify-content: space-around;
  flex-wrap: wrap;
}

.member {
  width: 30%;
  margin: 20px;
  text-align: center;
}

.member-image {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  object-fit: cover;
}

.member h3 {
  margin-top: 10px;
}

.member p {
  margin-top: 5px;
}

.footer {
  background-color: #f8f9fa;
  padding: 10px;
  text-align: center;
}

/* 加粗并增大名字显示 */
.highlight-teacher h3 {
  font-size: 1.5em; /* 根据需要调整大小 */
  font-weight: bold;
  color:rgb(139, 0, 0);
}

/* 加粗并适当增大角色显示 */
.highlight-teacher p:first-of-type {
  font-size: 1.2em; /* 根据需要调整大小 */
  font-weight: bold;
  color:rgb(139, 0, 0);
}
</style>